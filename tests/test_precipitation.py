"""Precipitation amounts (#86): forecast[].precipitation and hourly[].precipitation from every provider."""

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import helpers  # noqa: F401 (puts app/ on the path)

import outpost_updater as u
import units
from providers import hourly, metno, nws, openmeteo, pirateweather

NOW = datetime(2026, 7, 15, 14, 20, tzinfo=timezone.utc)


class AmountTests(unittest.TestCase):
    def test_an_amount(self):
        self.assertEqual(hourly.amount(0.25), 0.25)
        self.assertEqual(hourly.amount(-0.01), 0.0)
        for value in (None, "0.1", True, float("nan")):
            with self.subTest(value=value):
                self.assertIsNone(hourly.amount(value))

    def test_an_hour_has_one(self):
        self.assertEqual(hourly.entry(NOW, 70, "Rain", "rain", 80, 5, 180, 0.12)["precipitation"], 0.12)
        self.assertIsNone(hourly.entry(NOW, 70, "Clear", "sunny")["precipitation"])

    def test_units(self):
        data = {"forecast": [{"day": "2026-07-15", "precipitation": 0.256}],
                "hourly": [hourly.entry(NOW, 70, "Rain", "rain", precipitation=0.04)]}
        self.assertEqual(units.present(data, "imperial")["forecast"][0]["precipitation"], 0.26)
        metric = units.present(data, "metric")
        self.assertEqual(metric["forecast"][0]["precipitation"], 6.5)
        self.assertEqual(metric["hourly"][0]["precipitation"], 1.0)


class OpenMeteoTests(unittest.TestCase):
    def test_asks_for_amounts_in_inches(self):
        self.assertIn("precipitation_sum", openmeteo.DAILY_VARS)
        self.assertIn("precipitation", openmeteo.HOURLY_VARS)

    def test_daily_and_hourly(self):
        raw = {
            "utc_offset_seconds": 0,
            "current": {"time": "2026-07-15T14:15", "weather_code": 61},
            "daily": {"time": ["2026-07-15", "2026-07-16"], "precipitation_sum": [0.31, 0.0]},
            "hourly": {"time": ["2026-07-15T14:00", "2026-07-15T15:00"], "precipitation": [0.05, None]},
        }
        result = openmeteo.normalize(raw, NOW)
        self.assertEqual([day["precipitation"] for day in result["forecast"]], [0.31, 0.0])
        self.assertEqual([hour["precipitation"] for hour in result["hourly"]], [0.05, None])


class MetNorwayTests(unittest.TestCase):
    @staticmethod
    def entry(time, one=None, six=None):
        data = {"instant": {"details": {"air_temperature": 15.0}}}
        if one is not None:
            data["next_1_hours"] = {"summary": {"symbol_code": "rain"}, "details": {"precipitation_amount": one}}
        if six is not None:
            data["next_6_hours"] = {"summary": {"symbol_code": "rain"}, "details": {"precipitation_amount": six}}
        return {"time": time, "data": data}

    def test_hours_then_six_hour_steps_counting_no_time_twice(self):
        timeseries = [
            # Hourly entries also carry a 6-hour amount, which overlaps the hours after them
            self.entry("2026-07-15T22:00:00Z", one=1.0, six=9.0),
            self.entry("2026-07-15T23:00:00Z", one=1.54, six=9.0),
            self.entry("2026-07-16T00:00:00Z", six=6.0),
            self.entry("2026-07-16T06:00:00Z", six=0.0),
            self.entry("2026-07-16T12:00:00Z", six=4.0),
            self.entry("2026-07-17T00:00:00Z"),
        ]
        forecast = metno.build_forecast(timeseries, timezone.utc, NOW.date())
        self.assertEqual([day["day"] for day in forecast], ["2026-07-15", "2026-07-16", "2026-07-17"])
        self.assertAlmostEqual(forecast[0]["precipitation"], 2.54 / 25.4)
        self.assertAlmostEqual(forecast[1]["precipitation"], 10.0 / 25.4)
        # No amount given for that day
        self.assertIsNone(forecast[2]["precipitation"])

    def test_hourly(self):
        result = metno.build_hourly([self.entry("2026-07-15T14:00:00Z", one=2.54)], NOW)
        self.assertAlmostEqual(result[0]["precipitation"], 0.1)


class PirateWeatherTests(unittest.TestCase):
    def test_intensity_is_water(self):
        start = int(NOW.replace(hour=5, minute=0).timestamp())
        days = [{"time": start, "precipIntensity": 0.01, "precipAccumulation": 2.4},
                {"time": start + 86400}]
        forecast = pirateweather.build_forecast(days, ZoneInfo("UTC"))
        self.assertAlmostEqual(forecast[0]["precipitation"], 0.24)
        self.assertIsNone(forecast[1]["precipitation"])
        hours = pirateweather.build_hourly([{"time": int(NOW.replace(minute=0).timestamp()), "precipIntensity": 0.03}], NOW)
        self.assertEqual(hours[0]["precipitation"], 0.03)


class NwsTests(unittest.TestCase):
    def test_none_from_nws_so_gap_fill_takes_them(self):
        data = u.gapfill.fill({"current": {}, "forecast": [{"day": "2026-07-15", "precipitation": None}]},
                              {"forecast": [{"day": "2026-07-15", "precipitation": 0.4}]})
        self.assertEqual(data[0]["forecast"][0]["precipitation"], 0.4)
        self.assertEqual(data[1], ["forecast.precipitation"])

    def test_the_forecast_leaves_it_empty(self):
        periods = [{"startTime": "2026-07-15T06:00:00-05:00", "isDaytime": True, "temperature": 80,
                    "shortForecast": "Rain", "probabilityOfPrecipitation": {"value": 70}}]
        self.assertIsNone(nws.build_forecast(periods)[0]["precipitation"])


class PayloadTests(unittest.TestCase):
    def test_the_mock_has_amounts(self):
        payload = u.build_mock_payload()
        self.assertEqual(payload["units"]["precipitation"], "in")
        self.assertIn("precipitation", payload["forecast"][0])
        self.assertIn("precipitation", payload["hourly"][0])


if __name__ == "__main__":
    unittest.main()
