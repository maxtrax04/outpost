"""Unit systems (app/units.py) and the OUTPOST_UNITS setting."""

import unittest
from unittest import mock

import helpers

import outpost_updater as u
import units
from test_updater import UpdaterTestCase, nws_data, openmeteo_data


class ConvertTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(units.block("imperial"), {"system": "imperial", "temperature": "°F", "speed": "mph",
                                                   "pressure": "inHg", "distance": "mi"})
        self.assertEqual(units.block("metric"), {"system": "metric", "temperature": "°C", "speed": "km/h",
                                                 "pressure": "hPa", "distance": "km"})

    def test_metric_conversions(self):
        cases = [
            (32, "temperature", 0), (212, "temperature", 100), (0, "temperature", -18), (-40, "temperature", -40),
            (10, "speed", 16), (60, "speed", 97),
            (29.92, "pressure", 1013), (30.0, "pressure", 1016),
            (10, "distance", 16.1), (0.5, "distance", 0.8),
        ]
        for value, kind, expected in cases:
            with self.subTest(value=value, kind=kind):
                self.assertEqual(units.convert(value, kind, "metric"), expected)

    def test_imperial_is_only_rounded(self):
        self.assertEqual(units.convert(84.26, "temperature", "imperial"), 84)
        self.assertEqual(units.convert(29.9234, "pressure", "imperial"), 29.92)
        self.assertEqual(units.convert(9.94, "distance", "imperial"), 9.9)

    def test_whole_numbers_are_integers(self):
        self.assertIsInstance(units.convert(71.6, "temperature", "metric"), int)
        self.assertIsInstance(units.convert(10.4, "speed", "imperial"), int)

    def test_no_negative_zero(self):
        self.assertEqual(str(units.convert(-0.01, "distance", "metric")), "0.0")
        self.assertEqual(str(units.convert(31.9, "temperature", "metric")), "0")

    def test_missing_or_unusable_values_become_null(self):
        for value in (None, "70", True, [70]):
            with self.subTest(value=value):
                self.assertIsNone(units.convert(value, "temperature", "metric"))

    def test_present_converts_every_reading_and_nothing_else(self):
        data = {
            "current": {"temperature": 50, "feels_like": 41, "wind_speed": 25, "pressure": 30.12, "visibility": 3,
                        "humidity": 40, "uv_index": 3, "condition": "Windy", "icon": "wind"},
            "forecast": [{"day": "2026-01-01", "high": 59, "low": 23, "precipitation_chance": 20, "uv_index": 2}],
        }
        result = units.present(data, "metric")
        self.assertEqual(result["current"], {"temperature": 10, "feels_like": 5, "wind_speed": 40, "pressure": 1020,
                                             "visibility": 4.8, "humidity": 40, "uv_index": 3, "condition": "Windy",
                                             "icon": "wind"})
        self.assertEqual(result["forecast"][0], {"day": "2026-01-01", "high": 15, "low": -5,
                                                 "precipitation_chance": 20, "uv_index": 2})
        self.assertEqual(data["current"]["temperature"], 50)  # the input is not changed

    def test_every_converted_field_is_in_the_schema(self):
        self.assertLessEqual(set(units.CURRENT_FIELDS), set(u.build_mock_payload()["current"]))
        self.assertLessEqual(set(units.FORECAST_FIELDS), set(u.build_mock_payload()["forecast"][0]))


class SettingTests(unittest.TestCase):
    def setUp(self):
        self.print = mock.patch("builtins.print").start()
        self.addCleanup(mock.patch.stopall)

    def test_default_is_imperial(self):
        self.assertEqual(u.units_setting(None), "imperial")
        self.assertEqual(u.units_setting("  "), "imperial")

    def test_metric(self):
        self.assertEqual(u.units_setting("metric"), "metric")
        self.assertEqual(u.units_setting(" Metric "), "metric")
        self.print.assert_not_called()

    def test_unknown_value_warns_and_uses_imperial(self):
        self.assertEqual(u.units_setting("kelvin"), "imperial")
        self.assertIn("OUTPOST_UNITS", self.print.call_args[0][0])


class MetricPayloadTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.object(u, "UNITS", "metric").start()

    def test_labels_and_values_are_metric(self):
        payload = u.build_live_payload("openmeteo", openmeteo_data())
        self.assertEqual(payload["units"]["system"], "metric")
        self.assertEqual(payload["units"]["temperature"], "°C")
        current = payload["current"]
        self.assertEqual(current["temperature"], 29)   # 84.3 °F
        self.assertEqual(current["pressure"], 1012)    # Open-Meteo sent 1012.4 hPa
        self.assertEqual(payload["forecast"][0]["high"], 31)  # 88.2 °F

    def test_nws_values_are_metric(self):
        current = u.build_live_payload("nws", nws_data())["current"]
        self.assertEqual(current["temperature"], 29)   # the station reports 28.9 °C
        self.assertEqual(current["visibility"], 16.1)  # 16,090 m

    def test_mock_data_is_metric(self):
        for _ in range(20):
            payload = u.build_mock_payload()
            self.assertTrue(10 <= payload["current"]["temperature"] <= 35, payload["current"]["temperature"])
            self.assertTrue(950 <= payload["current"]["pressure"] <= 1050, payload["current"]["pressure"])

    def test_switching_units_does_not_reuse_data_in_the_old_units(self):
        with mock.patch.object(u, "UNITS", "imperial"), mock.patch.object(u, "PROVIDER", "openmeteo"), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        with mock.patch.object(u, "PROVIDER", "openmeteo"), \
                mock.patch.object(u.openmeteo, "fetch", side_effect=RuntimeError("boom")):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["units"]["system"], "metric")


if __name__ == "__main__":
    unittest.main()
