import io
import json
import unittest
import urllib.error
from unittest import mock

import helpers
from helpers import load_fixture
from providers import openmeteo


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.raw = load_fixture("openmeteo.json")

    def test_current_values(self):
        current = openmeteo.normalize(self.raw)["current"]
        self.assertEqual(current["temperature_f"], 84)
        self.assertEqual(current["feels_like_f"], 80)
        self.assertEqual(current["humidity_percent"], 12)
        self.assertEqual(current["wind_mph"], 10)
        self.assertEqual(current["pressure_inhg"], 29.9)
        self.assertEqual(current["visibility_miles"], 15.0)
        self.assertEqual(current["condition"], "Mainly clear")
        self.assertEqual(current["icon"], "sunny")

    def test_uv_comes_from_the_current_hour(self):
        self.assertEqual(openmeteo.normalize(self.raw)["current"]["uv_index"], 6)

    def test_forecast(self):
        forecast = openmeteo.normalize(self.raw)["forecast"]
        self.assertEqual(len(forecast), 5)
        self.assertEqual(forecast[0]["day"], "2026-07-15")
        self.assertEqual([d["high_f"] for d in forecast], [88, 86, 84, 79, 82])
        self.assertEqual([d["low_f"] for d in forecast], [60, 59, 58, 55, 57])
        self.assertEqual([d["icon"] for d in forecast], ["sunny", "partly-cloudy", "cloudy", "rain", "storm"])
        self.assertEqual([d["precipitation_percent"] for d in forecast], [0, 5, 10, 60, 40])

    def test_no_alerts_are_reported(self):
        self.assertEqual(openmeteo.normalize(self.raw)["alerts"], [])

    def test_source_attribution(self):
        self.assertEqual(openmeteo.normalize(self.raw)["source"], "Open-Meteo.com")

    def test_night_uses_night_icons(self):
        self.raw["current"]["is_day"] = 0
        self.assertEqual(openmeteo.normalize(self.raw)["current"]["icon"], "clear-night")
        self.raw["current"]["weather_code"] = 2
        self.assertEqual(openmeteo.normalize(self.raw)["current"]["icon"], "partly-cloudy-night")

    def test_night_leaves_other_icons_alone(self):
        self.raw["current"]["is_day"] = 0
        self.raw["current"]["weather_code"] = 61
        self.assertEqual(openmeteo.normalize(self.raw)["current"]["icon"], "rain")

    def test_freezing_rain_and_drizzle_icons(self):
        self.assertEqual(openmeteo.describe(53)[1], "drizzle")
        self.assertEqual(openmeteo.describe(66)[1], "sleet")

    def test_unknown_code(self):
        self.assertEqual(openmeteo.describe(12345), ("Unknown", "unknown"))

    def test_missing_optional_values_become_none(self):
        self.raw["hourly"]["visibility"] = [None] * 24
        del self.raw["daily"]["uv_index_max"]
        result = openmeteo.normalize(self.raw)
        self.assertIsNone(result["current"]["visibility_miles"])
        self.assertIsNone(result["forecast"][0]["uv_index"])

    def test_missing_sections_raise(self):
        del self.raw["current"]
        with self.assertRaises(RuntimeError):
            openmeteo.normalize(self.raw)


class FetchTests(unittest.TestCase):
    def test_request_has_location_and_user_agent(self):
        body = io.BytesIO(json.dumps(load_fixture("openmeteo.json")).encode())
        with mock.patch("urllib.request.urlopen", return_value=body) as urlopen:
            openmeteo.fetch_raw(10.0, 20.0, "Outpost-Test (test@example.com)")
        request = urlopen.call_args[0][0]
        self.assertIn("latitude=10.0", request.full_url)
        self.assertIn("longitude=20.0", request.full_url)
        self.assertIn("temperature_unit=fahrenheit", request.full_url)
        self.assertEqual(request.get_header("User-agent"), "Outpost-Test (test@example.com)")

    def test_http_error_includes_the_reason(self):
        error = urllib.error.HTTPError(
            "http://example.invalid", 400, "Bad Request", {}, io.BytesIO(b'{"reason": "Latitude out of range"}')
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                openmeteo.fetch_raw(10.0, 20.0, "test")
        self.assertIn("Latitude out of range", str(caught.exception))

    def test_network_error_is_reported(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
            with self.assertRaises(RuntimeError) as caught:
                openmeteo.fetch_raw(10.0, 20.0, "test")
        self.assertIn("unreachable", str(caught.exception))

    def test_error_flag_in_a_200_response(self):
        body = io.BytesIO(b'{"error": true, "reason": "nope"}')
        with mock.patch("urllib.request.urlopen", return_value=body):
            with self.assertRaises(RuntimeError):
                openmeteo.fetch_raw(10.0, 20.0, "test")


if __name__ == "__main__":
    unittest.main()
