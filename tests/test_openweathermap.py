"""OpenWeatherMap provider (app/providers/openweathermap.py), and how the updater uses it."""

import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
import units
from providers import openweathermap as owm
from test_updater import UpdaterTestCase, openmeteo_data

NOW = datetime(2026, 11, 13, 20, 10, tzinfo=timezone.utc)  # current.dt is 20:00 UTC
KEY = "owm-secret-key-123"


def owm_data():
    return owm.normalize(load_fixture("openweathermap.json"), now=NOW)


class NormalizeTests(unittest.TestCase):
    def test_capabilities(self):
        self.assertEqual(owm.CAPABILITIES, {"current", "forecast", "uv"})
        self.assertEqual(owm_data()["alerts"], [])
        self.assertEqual(owm_data()["source"], "OpenWeather")
        self.assertEqual(owm_data()["timezone"], "America/Chicago")

    def test_current(self):
        current = owm_data()["current"]
        self.assertEqual((current["temperature"], current["feels_like"], current["dew_point"]), (58.3, 56.9, 38.2))
        self.assertEqual((current["humidity"], current["wind_speed"], current["wind_gust"]), (47, 11.6, 20.3))
        self.assertEqual(current["wind_direction"], 210)
        self.assertEqual(current["uv_index"], 3)
        self.assertEqual((current["condition"], current["icon"]), ("Scattered clouds", "partly-cloudy"))
        self.assertEqual(current["observed_at"], "2026-11-13T20:00:00+00:00")
        shown = units.present({"current": current, "forecast": []}, "imperial")["current"]
        self.assertEqual(shown["pressure"], 29.92)  # 1013.2 hPa
        self.assertEqual(shown["visibility"], 6.2)  # 10,000 metres
        metric = units.present({"current": current, "forecast": []}, "metric")["current"]
        self.assertEqual(metric["visibility"], 10.0)

    def test_forecast(self):
        forecast = owm_data()["forecast"]
        self.assertEqual([day["day"] for day in forecast],
                         ["2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17"])  # 5 of 6
        self.assertEqual((forecast[0]["high"], forecast[0]["low"]), (61.7, 39.6))
        self.assertEqual([day["precipitation_chance"] for day in forecast], [5, 90, 62, 48, 0])
        self.assertEqual([day["icon"] for day in forecast], ["partly-cloudy", "rain", "storm", "snow", "sunny"])
        self.assertEqual([day["uv_index"] for day in forecast], [3, 1, 2, 1, 4])
        # Millimetres of rain, and of snow as water, in inches
        self.assertEqual([day["precipitation"] for day in forecast], [None, 0.25, 0.1, 0.2, None])
        # A long description gives way to the code's own text
        self.assertEqual(forecast[2]["condition"], "Thunderstorms")
        self.assertEqual(forecast[1]["condition"], "Moderate rain")

    def test_hourly(self):
        hourly = owm_data()["hourly"]
        self.assertEqual([hour["time"][11:16] for hour in hourly], ["20:00", "21:00", "22:00", "23:00"])
        self.assertEqual([hour["precipitation_chance"] for hour in hourly], [5, 40, 60, 0])
        self.assertEqual([hour["icon"] for hour in hourly], ["partly-cloudy", "rain", "sleet", "clear-night"])
        self.assertEqual([hour["precipitation"] and round(hour["precipitation"], 3) for hour in hourly],
                         [None, 0.03, 0.1, None])  # millimetres of rain and snow together, in inches
        self.assertEqual((hourly[1]["wind_speed"], hourly[1]["wind_direction"]), (12.0, 220))
        # Hours that have ended are left out
        later = owm.normalize(load_fixture("openweathermap.json"), now=datetime(2026, 11, 13, 23, 30, tzinfo=timezone.utc))
        self.assertEqual(len(later["hourly"]), 1)
        self.assertEqual(owm.build_hourly(None, NOW), [])

    def test_days_follow_the_locations_time_zone(self):
        raw = load_fixture("openweathermap.json")
        raw["timezone"] = "Not/AZone"
        raw["timezone_offset"] = 14 * 3600  # midday in Chicago is the next morning at UTC+14
        self.assertEqual(owm.normalize(raw, now=NOW)["forecast"][0]["day"], "2026-11-14")

    def test_conditions(self):
        cases = {
            (211, "11d"): "storm", (301, "09d"): "drizzle", (511, "13d"): "sleet", (502, "10n"): "rain",
            (611, "13d"): "sleet", (602, "13n"): "snow", (741, "50d"): "fog", (771, "50d"): "wind",
            (781, "50d"): "storm", (800, "01d"): "sunny", (800, "01n"): "clear-night",
            (801, "02n"): "partly-cloudy-night", (804, "04d"): "cloudy", (999, "01d"): "unknown",
        }
        for (code, icon), expected in cases.items():
            with self.subTest(code=code, icon=icon):
                self.assertEqual(owm.describe([{"id": code, "icon": icon}])[1], expected)
        for weather in (None, [], ["junk"], [{"id": "800"}], [{"id": True}]):
            with self.subTest(weather=weather):
                self.assertEqual(owm.describe(weather), ("Unknown", "unknown"))

    def test_missing_fields_are_none(self):
        raw = {"current": {}, "daily": [{"dt": 1794592800}, {"junk": 1}, "junk"]}
        data = owm.normalize(raw, now=NOW)
        self.assertTrue(all(value is None for key, value in data["current"].items() if key not in ("condition", "icon")))
        self.assertEqual(len(data["forecast"]), 1)
        self.assertIsNone(data["forecast"][0]["high"])
        self.assertEqual(data["hourly"], [])
        self.assertIsNone(data["timezone"])

    def test_missing_data_is_an_error(self):
        for raw in (None, {}, {"current": {}}, {"current": {}, "daily": []}, {"daily": [{}]}):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                owm.normalize(raw)


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode())
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class RequestTests(unittest.TestCase):
    def setUp(self):
        owm._cache.clear()
        self.addCleanup(owm._cache.clear)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(owm, "_blocked_until", 0.0).start()
        mock.patch.object(owm, "_blocked_reason", "").start()
        mock.patch.object(owm, "_calls", {"day": "", "calls": 0}).start()
        self.requests = []
        self.responses = []
        self.clock = NOW.timestamp()
        mock.patch.object(owm.time, "time", side_effect=lambda: self.clock).start()
        mock.patch.object(owm.urllib.request, "urlopen", side_effect=self.urlopen).start()

    def urlopen(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def ok(self):
        return FakeResponse(load_fixture("openweathermap.json"))

    def http_error(self, code, reason):
        return urllib.error.HTTPError(f"{owm.API_URL}?appid={KEY}", code, reason, {}, None)

    def test_the_request(self):
        self.responses = [self.ok()]
        owm.fetch_raw(39.123456, -98.5, KEY, "Outpost/1")
        url = self.requests[0].full_url
        self.assertTrue(url.startswith(owm.API_URL + "?"))
        for part in ("lat=39.1235", "lon=-98.5000", "units=imperial", "exclude=minutely", f"appid={KEY}"):
            self.assertIn(part, url)
        self.assertEqual(self.requests[0].get_header("User-agent"), "Outpost/1")
        # The cache is keyed without the key
        self.assertNotIn(KEY, repr(owm._cache.keys()))

    def test_an_answer_is_kept_for_ten_minutes(self):
        self.responses = [self.ok(), self.ok()]
        owm.fetch_raw(1, 2, KEY, "ua")
        self.clock += 599
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 2
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_one_minute_updates_stay_inside_the_free_calls(self):
        self.responses = [self.ok() for _ in range(300)]
        for _ in range(24 * 60):
            owm.fetch_raw(1, 2, KEY, "ua")
            self.clock += 60
        self.assertLessEqual(len(self.requests), 145)

    def test_never_more_than_the_daily_limit(self):
        self.clock = datetime(2026, 11, 13, 12, tzinfo=timezone.utc).timestamp()
        owm._calls.update({"day": "2026-11-13", "calls": owm.DAILY_CALL_LIMIT})
        with self.assertRaisesRegex(RuntimeError, "midnight UTC"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(self.requests, [])
        # A new UTC day starts again
        self.clock = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc).timestamp()
        self.responses = [self.ok()]
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(owm.calls_today(self.clock), 1)
        self.assertLess(owm.DAILY_CALL_LIMIT, 1000)

    def test_without_a_key_nothing_is_sent(self):
        with self.assertRaisesRegex(RuntimeError, "OUTPOST_OPENWEATHERMAP_API_KEY"):
            owm.fetch_raw(1, 2, "", "ua")
        self.assertEqual(self.requests, [])

    def test_errors_never_show_the_key_or_the_address(self):
        errors = [self.http_error(401, "Unauthorized"), self.http_error(429, "Too Many"),
                  self.http_error(500, f"Server error for {owm.API_URL}?appid={KEY}"),
                  urllib.error.URLError(f"failed {owm.API_URL}?appid={KEY}"), urllib.error.URLError(OSError("no route")),
                  TimeoutError("timed out")]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                owm._cache.clear()
                owm._blocked_until = 0.0
                self.responses = [error]
                with self.assertRaises(RuntimeError) as caught:
                    owm.fetch_raw(1, 2, KEY, "ua")
                self.assertNotIn(KEY, str(caught.exception))
                self.assertNotIn("appid", str(caught.exception))
                # Not chained, so a printed traceback can't show the address either
                self.assertIsNone(caught.exception.__cause__)

    def test_a_refused_key_is_not_tried_again_for_ten_minutes(self):
        self.responses = [self.http_error(401, "Unauthorized"), self.ok()]
        with self.assertRaisesRegex(RuntimeError, "OUTPOST_OPENWEATHERMAP_API_KEY"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.clock += 540
        with self.assertRaisesRegex(RuntimeError, "refused"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 61
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_too_many_requests_backs_off(self):
        self.responses = [self.http_error(429, "Too Many"), self.ok()]
        with self.assertRaisesRegex(RuntimeError, "429"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.clock += 3500
        with self.assertRaisesRegex(RuntimeError, "too many"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 101
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_invalid_json(self):
        response = FakeResponse({})
        response.seek(0)
        response.write(b"not json")
        response.truncate()
        response.seek(0)
        self.responses = [response]
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            owm.fetch_raw(1, 2, KEY, "ua")

    def test_weather_and_alerts_share_one_call(self):
        self.responses = [self.ok()]
        owm.fetch_alerts(1, 2, KEY, "ua")
        owm.fetch(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 1)


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.alerts = owm.build_alerts(load_fixture("openweathermap.json"))

    def test_most_serious_first_and_repeats_dropped(self):
        self.assertEqual([a["title"] for a in self.alerts], ["Winter Storm Warning", "Wind Advisory"])

    def test_fields(self):
        wind = self.alerts[1]
        self.assertEqual(wind["severity"], "minor")
        self.assertEqual(wind["description"], "South winds 25 to 35 mph with gusts up to 50 mph.")
        self.assertEqual(wind["onset"], "2026-11-13T20:00:00+00:00")
        self.assertEqual(wind["expires"], "2026-11-14T02:00:00+00:00")
        self.assertIsNone(wind["uri"])

    def test_severity_from_the_event_name(self):
        cases = {"Red Wind Warning": "extreme", "Extreme Heat Warning": "extreme",
                 "Orange Rain Warning": "severe", "Amber warning for snow": "severe",
                 "Yellow Thunderstorm Warning": "moderate", "Flood Warning": "severe",
                 "Winter Storm Watch": "moderate", "Wind Advisory": "minor",
                 "Special Weather Statement": "minor", "Avis de gel": "unknown", "": "unknown",
                 "Frost": "unknown", "Red-flag": "extreme"}
        for event, expected in cases.items():
            with self.subTest(event=event):
                self.assertEqual(owm.severity(event), expected)

    def test_no_alerts(self):
        for raw in (None, {}, {"alerts": None}, {"alerts": []}, {"alerts": ["junk"]}):
            with self.subTest(raw=raw):
                self.assertEqual(owm.build_alerts(raw), [])

    def test_missing_times_and_at_most_five(self):
        only = owm.build_alerts({"alerts": [{"event": "Frost"}]})[0]
        self.assertEqual((only["onset"], only["expires"], only["severity"]), (None, None, "unknown"))
        self.assertEqual(owm.build_alerts({"alerts": [{}]})[0]["title"], "Weather alert")
        many = {"alerts": [{"event": f"Alert {n}"} for n in range(9)]}
        self.assertEqual(len(owm.build_alerts(many)), owm.MAX_ALERTS)


class UpdaterTests(UpdaterTestCase):
    ALERTS = [{"title": "Storm Warning", "description": "", "severity": "severe", "onset": None,
               "expires": None, "uri": None}]

    def setUp(self):
        super().setUp()
        self.owm_alerts.return_value = self.ALERTS

    def run_update(self, key=KEY, provider="openweathermap", alerts_provider="auto", location=None, state=None):
        with mock.patch.object(u, "PROVIDER", provider), mock.patch.object(u, "ALERTS_PROVIDER", alerts_provider), \
                mock.patch.object(u, "OPENWEATHERMAP_API_KEY", key), \
                mock.patch.object(u, "THEMES_DIR", helpers.ROOT / "web" / "themes"), \
                mock.patch.object(u, "CONFIG_PATH", self.data_dir / "config.json", create=True), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()), \
                mock.patch.object(u.openweathermap, "fetch", return_value=owm_data()) as fetch:
            result = u.update_once(location, state) if location else u.update_once()
        return (result if location else self.output()), fetch

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)

    def test_openweathermap(self):
        data, fetch = self.run_update()
        fetch.assert_called_once_with(u.LATITUDE, u.LONGITUDE, KEY, u.USER_AGENT)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sources"]["weather"], {"id": "openweathermap", "name": "OpenWeather"})
        self.assertEqual(data["timezone"], "America/Chicago")

    def test_outside_the_us_its_own_alerts_are_used(self):
        data, _ = self.run_update()
        self.owm_alerts.assert_called_once()
        self.assertEqual(data["sources"]["alerts"], {"id": "openweathermap", "name": "OpenWeather"})
        self.assertEqual(data["alerts"], self.ALERTS)

    def test_in_the_us_nws_alerts_come_first(self):
        self.nws_alerts.side_effect = None
        self.nws_alerts.return_value = []
        data, _ = self.run_update()
        self.owm_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")

    def test_other_weather_providers_never_use_its_alerts_under_auto(self):
        data, _ = self.run_update(provider="openmeteo")
        self.owm_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_it_can_be_chosen_for_alerts(self):
        self.nws_alerts.side_effect = None
        data, _ = self.run_update(provider="openmeteo", alerts_provider="openweathermap")
        self.nws_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "openweathermap")

    def test_choosing_it_for_alerts_without_a_key_warns_once(self):
        self.run_update(key="", provider="openmeteo", alerts_provider="openweathermap")
        data, _ = self.run_update(key="", provider="openmeteo", alerts_provider="openweathermap")
        self.owm_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(self.printed().count("needs OUTPOST_OPENWEATHERMAP_API_KEY"), 1)

    def test_the_setting_is_known(self):
        self.assertEqual(u.alerts_provider_setting("OpenWeatherMap"), "openweathermap")

    def test_other_places_never_use_the_key(self):
        elsewhere = u.Location(50.0, 10.0, "Fictional Town")
        self.assertEqual(u.openweathermap_key(elsewhere), "")
        data, fetch = self.run_update(location=elsewhere, state=u.LocationState())
        fetch.assert_not_called()
        self.owm_alerts.assert_not_called()
        self.assertEqual(data["sources"]["weather"]["id"], "openmeteo")
        data, _ = self.run_update(provider="openmeteo", alerts_provider="openweathermap", location=elsewhere,
                                  state=u.LocationState())
        self.owm_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_never_part_of_auto(self):
        with mock.patch.object(u, "OPENWEATHERMAP_API_KEY", KEY), mock.patch.object(u, "PIRATEWEATHER_API_KEY", ""), \
                mock.patch.object(u, "PROVIDER", "auto"), \
                mock.patch.object(u.nws, "fetch", side_effect=u.nws.NoCoverageError("US only")), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()), \
                mock.patch.object(u.openweathermap, "fetch") as fetch:
            u.update_once()
        fetch.assert_not_called()
        self.owm_alerts.assert_not_called()
        self.assertEqual(self.output()["sources"]["weather"]["id"], "openmeteo")

    def test_the_key_is_never_written_out(self):
        self.run_update()
        for path in self.data_dir.iterdir():
            with self.subTest(file=path.name):
                self.assertNotIn(KEY, path.read_text(encoding="utf-8"))
        self.assertNotIn(KEY, self.printed())

    def test_a_failure_keeps_the_last_good_data(self):
        self.run_update()
        with mock.patch.object(u, "PROVIDER", "openweathermap"), mock.patch.object(u, "OPENWEATHERMAP_API_KEY", KEY), \
                mock.patch.object(u.openweathermap, "fetch", side_effect=RuntimeError("OpenWeatherMap HTTP 500")):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["last_error"], "OpenWeatherMap HTTP 500")
        self.assertEqual(data["sources"]["weather"]["id"], "openweathermap")

    def test_request_limits_are_listed(self):
        self.assertIn("OpenWeatherMap every 10 min", u.request_limits_text())


if __name__ == "__main__":
    unittest.main()
