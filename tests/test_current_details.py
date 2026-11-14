"""Reading time (current.observed_at), wind direction, and dew point from every provider."""

import unittest
from datetime import datetime

import helpers
from helpers import load_fixture

import outpost_updater as u
import units
from providers import gapfill, nws, openmeteo
from test_pirateweather import pirate_data
from test_updater import metno_data, nws_data, openmeteo_data


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "openmeteo": openmeteo_data(),
            "nws": nws_data(),
            "metno": metno_data(),
            "pirateweather": pirate_data(),
        }

    def test_wind_direction_in_degrees(self):
        expected = {"openmeteo": 225, "nws": 200, "metno": 212.0, "pirateweather": 210}
        for provider, degrees in expected.items():
            with self.subTest(provider=provider):
                self.assertEqual(self.data[provider]["current"]["wind_direction"], degrees)

    def test_dew_point_in_fahrenheit(self):
        expected = {"openmeteo": 26.4, "nws": -3.1 * 9 / 5 + 32, "metno": -4.9 * 9 / 5 + 32, "pirateweather": 38.2}
        for provider, fahrenheit in expected.items():
            with self.subTest(provider=provider):
                self.assertAlmostEqual(self.data[provider]["current"]["dew_point"], fahrenheit, places=3)

    def test_reading_time_in_utc(self):
        expected = {
            "openmeteo": "2026-07-15T14:15:00+00:00",   # the fixture is at UTC
            "metno": "2026-11-13T01:00:00+00:00",       # the forecast hour (the fixture's "now" is in it)
            "pirateweather": "2026-11-13T20:00:00+00:00",  # currently.time 1794600000
        }
        # nws_data() makes the station reading fresh, so it is the station's timestamp
        observation = nws.build_current([{}], {"timestamp": "2026-07-15T16:00:00-05:00"})
        self.assertEqual(observation["observed_at"], "2026-07-15T21:00:00+00:00")
        for provider, moment in expected.items():
            with self.subTest(provider=provider):
                observed = self.data[provider]["current"]["observed_at"]
                self.assertEqual(datetime.fromisoformat(observed), datetime.fromisoformat(moment))

    def test_open_meteo_local_time_is_turned_into_utc(self):
        self.assertEqual(openmeteo._observed_at("2026-07-15T14:15", 7200), "2026-07-15T12:15:00+00:00")
        self.assertEqual(openmeteo._observed_at("2026-07-15T14:15", -18000), "2026-07-15T19:15:00+00:00")
        self.assertIsNone(openmeteo._observed_at(None, 0))
        self.assertIsNone(openmeteo._observed_at("not a time", 0))

    def test_open_meteo_asks_for_them(self):
        self.assertIn("wind_direction_10m", openmeteo.CURRENT_VARS)
        self.assertIn("dew_point_2m", openmeteo.CURRENT_VARS)

    def test_nws_without_a_station_reading(self):
        periods = load_fixture("nws_forecast.json")["properties"]["periods"]
        current = nws.build_current(periods, None)
        self.assertEqual(current["wind_direction"], 225)  # "SW" from the forecast
        self.assertIsNone(current["dew_point"])
        self.assertIsNone(current["observed_at"])  # a forecast, not a reading

    def test_nws_calm_has_no_direction(self):
        observation = load_fixture("nws_observation.json")["properties"]
        observation["windDirection"] = {"unitCode": "wmoUnit:degree_(angle)", "value": None}
        periods = load_fixture("nws_forecast.json")["properties"]["periods"]
        self.assertIsNone(nws.build_current(periods, observation)["wind_direction"])

    def test_nws_compass_points(self):
        self.assertEqual(nws.COMPASS_DEGREES["N"], 0)
        self.assertEqual(nws.COMPASS_DEGREES["E"], 90)
        self.assertEqual(nws.COMPASS_DEGREES["NNW"], 337.5)
        self.assertEqual(len(nws.COMPASS_DEGREES), 16)


class UnitTests(unittest.TestCase):
    def present(self, current, system="imperial"):
        return units.present({"current": current, "forecast": []}, system)["current"]

    def test_dew_point_is_converted_like_temperature(self):
        self.assertEqual(self.present({"dew_point": 50})["dew_point"], 50)
        self.assertEqual(self.present({"dew_point": 50}, "metric")["dew_point"], 10)

    def test_wind_direction_is_whole_degrees_in_either_system(self):
        for system in units.SYSTEMS:
            with self.subTest(system=system):
                self.assertEqual(self.present({"wind_direction": 212.4}, system)["wind_direction"], 212)

    def test_wind_direction_wraps_to_north(self):
        self.assertEqual(units.direction(359.6), 0)
        self.assertEqual(units.direction(360), 0)
        self.assertEqual(units.direction(0), 0)

    def test_calm_has_no_direction(self):
        for system in units.SYSTEMS:
            with self.subTest(system=system):
                self.assertIsNone(self.present({"wind_speed": 0.3, "wind_direction": 0}, system)["wind_direction"])
                self.assertEqual(self.present({"wind_speed": 3, "wind_direction": 0}, system)["wind_direction"], 0)

    def test_wind_direction_that_is_not_a_number(self):
        for value in (None, "SW", True, float("nan")):
            with self.subTest(value=value):
                self.assertIsNone(units.direction(value))


class FillTests(unittest.TestCase):
    def test_dew_point_is_filled_but_direction_is_not(self):
        # A direction from one source beside a wind speed from another could be misleading
        primary = {"current": {"dew_point": None, "wind_direction": None}, "forecast": []}
        secondary = {"current": {"dew_point": 40, "wind_direction": 90}, "forecast": []}
        merged, filled = gapfill.fill(primary, secondary)
        self.assertEqual(merged["current"]["dew_point"], 40)
        self.assertIsNone(merged["current"]["wind_direction"])
        self.assertNotIn("wind_direction", gapfill.CURRENT_FIELDS)
        self.assertNotIn("observed_at", gapfill.CURRENT_FIELDS)


class PayloadTests(unittest.TestCase):
    def test_in_every_payload(self):
        for name in ("dew_point", "wind_direction", "observed_at"):
            with self.subTest(name=name):
                self.assertIn(name, u.build_error_payload("boom")["current"])

    def test_mock_values(self):
        for _ in range(20):
            current = u.build_mock_payload()["current"]
            self.assertLessEqual(current["dew_point"], current["temperature"])
            if current["wind_speed"] == 0:
                self.assertIsNone(current["wind_direction"])  # calm
            else:
                self.assertTrue(0 <= current["wind_direction"] <= 359)
            datetime.fromisoformat(current["observed_at"])


if __name__ == "__main__":
    unittest.main()
