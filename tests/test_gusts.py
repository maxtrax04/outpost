"""Wind gusts (current.wind_gust) from every provider, converted like wind speed."""

import unittest
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
import units
from providers import nws, openmeteo
from test_pirateweather import pirate_data
from test_updater import metno_data, nws_data, openmeteo_data


class ProviderTests(unittest.TestCase):
    def test_each_provider_reports_gusts_in_mph(self):
        cases = {
            "openmeteo": (openmeteo_data(), 21.7),        # requested in mph
            "nws": (nws_data(), 38.9 * nws.KMH_TO_MPH),    # 38.9 km/h from the station
            "metno": (metno_data(), 3.1 * 2.236936),       # 3.1 m/s
            "pirateweather": (pirate_data(), 20.3),        # requested in mph
        }
        for provider, (data, expected) in cases.items():
            with self.subTest(provider=provider):
                self.assertAlmostEqual(data["current"]["wind_gust"], expected, places=3)

    def test_open_meteo_asks_for_gusts(self):
        self.assertIn("wind_gusts_10m", openmeteo.CURRENT_VARS)

    def test_no_gusts_is_null(self):
        observation = load_fixture("nws_observation.json")["properties"]
        observation["windGust"] = {"unitCode": "wmoUnit:km_h-1", "value": None}  # calm: NWS sends no gust
        periods = load_fixture("nws_forecast.json")["properties"]["periods"]
        self.assertIsNone(nws.build_current(periods, observation)["wind_gust"])
        self.assertIsNone(nws.build_current(periods, None)["wind_gust"])  # no observation at all

    def test_gusts_are_never_filled_from_another_source(self):
        # A gust from one source beside a wind speed from another could be misleading
        self.assertNotIn("wind_gust", u.gapfill.CURRENT_FIELDS)


class UnitTests(unittest.TestCase):
    def test_converted_and_rounded_like_wind_speed(self):
        current = {"wind_speed": 10, "wind_gust": 25.4}
        self.assertEqual(units.present({"current": current, "forecast": []}, "imperial")["current"]["wind_gust"], 25)
        self.assertEqual(units.present({"current": current, "forecast": []}, "metric")["current"]["wind_gust"], 41)

    def test_in_every_payload(self):
        self.assertIn("wind_gust", u.build_error_payload("boom")["current"])
        for _ in range(20):
            current = u.build_mock_payload()["current"]
            self.assertGreaterEqual(current["wind_gust"], current["wind_speed"])


if __name__ == "__main__":
    unittest.main()
