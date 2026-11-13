"""Pirate Weather provider (app/providers/pirateweather.py), and how the updater uses it."""

import email.message
import io
import json
import unittest
import urllib.error
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
import units
from providers import nws, pirateweather
from test_updater import UpdaterTestCase, metno_data, nws_data, openmeteo_data


def pirate_data():
    return pirateweather.normalize(load_fixture("pirateweather.json"))


class NormalizeTests(unittest.TestCase):
    def test_capabilities(self):
        self.assertEqual(pirateweather.CAPABILITIES, {"current", "forecast", "uv"})
        self.assertEqual(pirate_data()["alerts"], [])
        self.assertEqual(pirate_data()["source"], "Pirate Weather")

    def test_current(self):
        current = pirate_data()["current"]
        self.assertEqual(current["temperature"], 58.3)
        self.assertEqual(current["feels_like"], 56.9)
        self.assertEqual(current["humidity"], 47)  # 0.47
        self.assertEqual(current["wind_speed"], 11.6)
        self.assertEqual(current["visibility"], 10.0)
        self.assertEqual(current["uv_index"], 3)
        self.assertEqual((current["condition"], current["icon"]), ("Partly Cloudy", "partly-cloudy"))
        shown = units.present({"current": current, "forecast": []}, "imperial")["current"]
        self.assertEqual(shown["pressure"], 29.92)  # 1013.2 millibars

    def test_forecast(self):
        forecast = pirate_data()["forecast"]
        self.assertEqual([day["day"] for day in forecast],
                         ["2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17"])
        self.assertEqual((forecast[0]["high"], forecast[0]["low"]), (61.7, 39.6))  # the calendar day's max and min
        self.assertEqual([day["precipitation_chance"] for day in forecast], [5, 90, 62, 48, 0])
        self.assertEqual([day["icon"] for day in forecast], ["partly-cloudy", "rain", "storm", "snow", "sunny"])
        self.assertEqual([day["uv_index"] for day in forecast], [3, 1, 2, 1, 4])

    def test_long_summaries_are_replaced_by_a_short_text(self):
        forecast = pirate_data()["forecast"]
        self.assertEqual(forecast[1]["condition"], "Rain")  # "Rain throughout the day, heaviest in the afternoon."
        self.assertEqual(forecast[2]["condition"], "Thunderstorms")

    def test_days_follow_the_locations_time_zone(self):
        raw = load_fixture("pirateweather.json")
        raw["timezone"] = "Not/AZone"
        raw["offset"] = 10.0  # midnight in Chicago is mid-afternoon at UTC+10
        self.assertEqual(pirateweather.normalize(raw)["forecast"][0]["day"], "2026-11-13")
        raw["offset"] = -12.0
        self.assertEqual(pirateweather.normalize(raw)["forecast"][0]["day"], "2026-11-12")

    def test_icons(self):
        for icon, expected in {"clear-night": "clear-night", "partly-cloudy-night": "partly-cloudy-night",
                               "sleet": "sleet", "hail": "sleet", "wind": "wind", "fog": "fog",
                               "none": "unknown", None: "unknown", "mostly-clear-day": "unknown"}.items():
            with self.subTest(icon=icon):
                self.assertEqual(pirateweather.describe(icon)[1], expected)

    def test_missing_data_is_an_error(self):
        for raw in ({}, {"currently": {}}, {"daily": {"data": [{}]}}):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                pirateweather.normalize(raw)


def headers(**values):
    message = email.message.Message()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


class FakeResponse(io.BytesIO):
    def __init__(self, body, header_values):
        super().__init__(json.dumps(body).encode())
        self.headers = header_values

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class RequestTests(unittest.TestCase):
    KEY = "secret-key-123"

    def setUp(self):
        pirateweather._cache.clear()
        mock.patch.object(pirateweather, "_blocked_until", 0.0).start()
        self.addCleanup(pirateweather._cache.clear)
        self.addCleanup(mock.patch.stopall)
        self.requests = []
        self.responses = []
        self.clock = 1_000_000.0
        mock.patch.object(pirateweather.time, "time", side_effect=lambda: self.clock).start()
        mock.patch.object(pirateweather.urllib.request, "urlopen", side_effect=self.urlopen).start()

    def urlopen(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def ok(self, cache_control=""):
        return FakeResponse(load_fixture("pirateweather.json"), headers(Cache_Control=cache_control))

    def test_the_key_is_sent_in_a_header_never_in_the_address(self):
        self.responses = [self.ok()]
        pirateweather.fetch_raw(39.123456, -98.5, self.KEY, "Outpost/1")
        request = self.requests[0]
        self.assertEqual(request.get_header("Apikey"), self.KEY)
        self.assertNotIn(self.KEY, request.full_url)
        self.assertIn("/39.1235,-98.5000?", request.full_url)
        self.assertIn("units=us", request.full_url)

    def test_a_forecast_is_kept_for_ten_minutes(self):
        self.responses = [self.ok(), self.ok()]
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.clock += 599
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 2
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_a_longer_cache_time_from_the_service_is_honored(self):
        self.responses = [self.ok("public, max-age=1800")]
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.clock += 1700
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 1)

    def test_one_minute_updates_stay_inside_the_free_quota(self):
        # A week of updates every minute; the free tier is 10,000 calls a month
        self.responses = [self.ok() for _ in range(2000)]
        for _ in range(7 * 24 * 60):
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")
            self.clock += 60
        self.assertLess(len(self.requests) * 30 / 7, 10_000)

    def test_without_a_key_nothing_is_sent(self):
        with self.assertRaisesRegex(RuntimeError, "OUTPOST_PIRATEWEATHER_API_KEY"):
            pirateweather.fetch_raw(1, 2, "", "ua")
        self.assertEqual(self.requests, [])

    def test_a_refused_key_says_what_to_check_without_showing_it(self):
        self.responses = [urllib.error.HTTPError("u", 401, "Unauthorized", headers(), None)]
        with self.assertRaises(RuntimeError) as caught:
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertIn("OUTPOST_PIRATEWEATHER_API_KEY", str(caught.exception))
        self.assertNotIn(self.KEY, str(caught.exception))

    def test_after_the_quota_runs_out_it_waits_for_the_reset(self):
        self.responses = [urllib.error.HTTPError("u", 429, "Too Many Requests", headers(Ratelimit_Reset="7200"), None),
                          self.ok()]
        with self.assertRaisesRegex(RuntimeError, "quota"):
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.clock += 7000
        with self.assertRaisesRegex(RuntimeError, "quota"):
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 1)  # no request while waiting
        self.clock += 201
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_unreachable(self):
        self.responses = [urllib.error.URLError("no route")]
        with self.assertRaisesRegex(RuntimeError, "unreachable"):
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")


class UpdaterTests(UpdaterTestCase):
    def test_pirateweather(self):
        with mock.patch.object(u, "PROVIDER", "pirateweather"), mock.patch.object(u, "PIRATEWEATHER_API_KEY", "k"), \
                mock.patch.object(u.pirateweather, "fetch", return_value=pirate_data()) as fetch:
            u.update_once()
        fetch.assert_called_once_with(u.LATITUDE, u.LONGITUDE, "k", u.USER_AGENT)
        data = self.output()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sources"]["weather"], {"id": "pirateweather", "name": "Pirate Weather"})

    def test_the_key_is_never_written_out(self):
        with mock.patch.object(u, "PROVIDER", "pirateweather"), mock.patch.object(u, "PIRATEWEATHER_API_KEY", "secret-key-123"), \
                mock.patch.object(u, "THEMES_DIR", helpers.ROOT / "web" / "themes"), \
                mock.patch.object(u, "CONFIG_PATH", self.data_dir / "config.json", create=True), \
                mock.patch.object(u.pirateweather, "fetch", return_value=pirate_data()):
            u.update_once()
        for path in self.data_dir.iterdir():
            with self.subTest(file=path.name):
                self.assertNotIn("secret-key-123", path.read_text(encoding="utf-8"))

    def run_auto(self, key, pirate=None, latitude=59.91, longitude=10.75):
        with mock.patch.object(u, "PROVIDER", "auto"), mock.patch.object(u, "PIRATEWEATHER_API_KEY", key), \
                mock.patch.object(u, "LATITUDE", latitude), mock.patch.object(u, "LONGITUDE", longitude), \
                mock.patch.object(u.pirateweather, "fetch", **(pirate or {"return_value": pirate_data()})) as pirate_fetch, \
                mock.patch.object(u.metno, "fetch", return_value=metno_data()), \
                mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        return self.output(), pirate_fetch

    def test_auto_tries_pirate_weather_first_when_a_key_is_set(self):
        data, pirate_fetch = self.run_auto("k")
        pirate_fetch.assert_called_once()
        self.assertEqual(data["sources"]["weather"]["id"], "pirateweather")

    def test_auto_without_a_key_never_uses_it(self):
        data, pirate_fetch = self.run_auto("")
        pirate_fetch.assert_not_called()
        self.assertEqual(data["sources"]["weather"]["id"], "metno")

    def test_auto_falls_back_when_pirate_weather_fails(self):
        data, _ = self.run_auto("k", pirate={"side_effect": RuntimeError("Pirate Weather HTTP 500")})
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sources"]["weather"]["id"], "metno")  # the Nordic choice for this location
        printed = " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)
        self.assertIn("Pirate Weather failed", printed)

    def test_auto_in_the_us_with_pirate_weather_still_gets_nws_alerts(self):
        self.nws_alerts.side_effect = None
        self.nws_alerts.return_value = [{"title": "Flood Watch", "description": "", "severity": "moderate",
                                         "expires": None, "uri": None}]
        data, _ = self.run_auto("k", latitude=39.0, longitude=-98.0)
        self.assertEqual(data["sources"]["weather"]["id"], "pirateweather")
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")


if __name__ == "__main__":
    unittest.main()
