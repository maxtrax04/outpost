"""The hourly forecast (#85): weather.json "hourly" from every provider (app/providers/hourly.py)."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers  # noqa: F401 (puts app/ on the path)

import outpost_updater as u
import units
from providers import hourly, metno, nws, openmeteo, pirateweather

NOW = datetime(2026, 7, 15, 14, 20, tzinfo=timezone.utc)
FIELDS = {"time", "temperature", "condition", "icon", "precipitation_chance", "wind_speed", "wind_direction"}


class UpcomingTests(unittest.TestCase):
    def hour(self, offset):
        return hourly.entry(NOW.replace(minute=0) + timedelta(hours=offset), 70, "Clear", "sunny")

    def test_from_the_hour_under_way_at_most_24(self):
        entries = [self.hour(offset) for offset in range(30, -3, -1)]  # out of order, with past hours
        result = hourly.upcoming(entries, NOW)
        self.assertEqual(len(result), hourly.HOURS)
        self.assertEqual(result[0]["time"], "2026-07-15T14:00:00+00:00")
        self.assertEqual(result[-1]["time"], "2026-07-16T13:00:00+00:00")

    def test_repeats_and_bad_times_are_left_out(self):
        entries = [self.hour(1), self.hour(1), {"time": "soon"}, {"time": "2026-07-15T18:00:00"}, {}]
        self.assertEqual([item["time"] for item in hourly.upcoming(entries, NOW)], ["2026-07-15T15:00:00+00:00"])

    def test_an_entry(self):
        item = hourly.entry(datetime(2026, 7, 15, 9, tzinfo=timezone(timedelta(hours=-5))), 71.5, "Rain", "rain",
                            140, True, float("nan"))
        self.assertEqual(set(item), FIELDS)
        self.assertEqual(item["time"], "2026-07-15T14:00:00+00:00")
        self.assertEqual(item["precipitation_chance"], 100)
        self.assertIsNone(item["wind_speed"])
        self.assertIsNone(item["wind_direction"])


class OpenMeteoTests(unittest.TestCase):
    def test_hours_in_utc_with_night_icons(self):
        raw = {
            "utc_offset_seconds": -18000,
            "hourly": {
                "time": ["2026-07-15T08:00", "2026-07-15T09:00", "2026-07-15T21:00"],
                "temperature_2m": [70.1, 72.4, 65.0],
                "weather_code": [0, 61, 2],
                "precipitation_probability": [0, 80, 10],
                "wind_speed_10m": [5.0, 9.5, 2.0],
                "wind_direction_10m": [180, 200, 90],
                "is_day": [1, 1, 0],
            },
        }
        result = openmeteo.build_hourly(raw, NOW)
        self.assertEqual([item["time"] for item in result],
                         ["2026-07-15T14:00:00+00:00", "2026-07-16T02:00:00+00:00"])
        self.assertEqual((result[0]["condition"], result[0]["icon"], result[0]["precipitation_chance"]),
                         ("Light rain", "rain", 80))
        self.assertEqual(result[1]["icon"], "partly-cloudy-night")
        self.assertEqual(result[0]["wind_direction"], 200)

    def test_missing_or_short_columns(self):
        self.assertEqual(openmeteo.build_hourly({}, NOW), [])
        raw = {"utc_offset_seconds": 0, "hourly": {"time": ["2026-07-15T15:00"], "temperature_2m": [1, 2]}}
        self.assertIsNone(openmeteo.build_hourly(raw, NOW)[0]["temperature"])

    def test_asks_for_the_hourly_readings(self):
        for name in ("temperature_2m", "weather_code", "precipitation_probability", "wind_speed_10m",
                     "wind_direction_10m", "is_day"):
            self.assertIn(name, openmeteo.HOURLY_VARS)


class NwsTests(unittest.TestCase):
    PERIODS = [
        {"startTime": "2026-07-15T08:00:00-05:00", "isDaytime": True, "temperature": 75, "temperatureUnit": "F",
         "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": 5}, "windSpeed": "5 mph",
         "windDirection": "S", "shortForecast": "Sunny"},
        {"startTime": "2026-07-15T09:00:00-05:00", "isDaytime": True, "temperature": 24, "temperatureUnit": "C",
         "probabilityOfPrecipitation": {"value": None}, "windSpeed": "10 to 15 mph", "windDirection": "WSW",
         "shortForecast": "Chance Showers And Thunderstorms"},
        {"startTime": "2026-07-15T21:00:00-05:00", "isDaytime": False, "temperature": 68, "windSpeed": "0 mph",
         "windDirection": "", "shortForecast": "Mostly Clear"},
        {"startTime": "not a time"},
    ]

    def test_periods(self):
        result = nws.build_hourly(self.PERIODS, NOW)
        self.assertEqual(len(result), 2)
        first, night = result
        self.assertEqual(first["time"], "2026-07-15T14:00:00+00:00")
        self.assertAlmostEqual(first["temperature"], 75.2)
        self.assertEqual((first["icon"], first["precipitation_chance"], first["wind_speed"], first["wind_direction"]),
                         ("storm", None, 15, 247.5))
        self.assertEqual((night["icon"], night["wind_direction"]), ("clear-night", None))

    def test_a_failed_hourly_forecast_leaves_it_out(self):
        point = {"hourly_url": "https://api.weather.gov/gridpoints/X/1,2/forecast/hourly"}
        with mock.patch.object(nws, "_cached_get", side_effect=RuntimeError("NWS HTTP 500")), \
                mock.patch("sys.stderr"):
            self.assertEqual(nws._hourly(point, "ua"), [])
        self.assertEqual(nws._hourly({}, "ua"), [])
        with mock.patch.object(nws, "_cached_get", return_value={"properties": {"periods": self.PERIODS}}), \
                mock.patch.object(nws.hours, "upcoming", side_effect=lambda entries, now=None: entries):
            self.assertEqual(len(nws._hourly(point, "ua")), 3)


class MetNorwayTests(unittest.TestCase):
    def test_entries_with_a_one_hour_forecast(self):
        timeseries = [
            {"time": "2026-07-15T14:00:00Z", "data": {
                "instant": {"details": {"air_temperature": 20.0, "wind_speed": 4.0, "wind_from_direction": 270.0}},
                "next_1_hours": {"summary": {"symbol_code": "lightrainshowers_day"},
                                 "details": {"probability_of_precipitation": 40.0}}}},
            {"time": "2026-07-15T15:00:00Z", "data": {
                "instant": {"details": {"air_temperature": 19.0}},
                "next_1_hours": {"summary": {"symbol_code": "clearsky_night"}}}},
            {"time": "2026-07-18T00:00:00Z", "data": {
                "instant": {"details": {"air_temperature": 15.0}},
                "next_6_hours": {"summary": {"symbol_code": "cloudy"}}}},
        ]
        result = metno.build_hourly(timeseries, NOW)
        self.assertEqual(len(result), 2)
        self.assertEqual((result[0]["temperature"], result[0]["icon"], result[0]["precipitation_chance"]),
                         (68.0, "rain", 40))
        self.assertAlmostEqual(result[0]["wind_speed"], 8.947744)
        self.assertEqual((result[1]["icon"], result[1]["precipitation_chance"]), ("clear-night", None))
        self.assertEqual(metno.normalize({"properties": {"timeseries": timeseries}}, now=NOW)["hourly"], result)


class PirateWeatherTests(unittest.TestCase):
    def test_hours(self):
        start = int(NOW.replace(minute=0).timestamp())
        data = [
            {"time": start - 3600, "icon": "clear-day", "temperature": 80},
            {"time": start, "icon": "rain", "summary": "Rain", "temperature": 78.5, "precipProbability": 0.62,
             "windSpeed": 7.2, "windBearing": 135},
            {"time": start + 3600, "icon": "partly-cloudy-night", "temperature": 70},
            "not an hour",
        ]
        result = pirateweather.build_hourly(data, NOW)
        self.assertEqual([item["time"][11:16] for item in result], ["14:00", "15:00"])
        self.assertEqual((result[0]["condition"], result[0]["precipitation_chance"], result[0]["wind_direction"]),
                         ("Rain", 62, 135))
        self.assertEqual(result[1]["icon"], "partly-cloudy-night")
        self.assertEqual(pirateweather.build_hourly(None, NOW), [])


class PayloadTests(unittest.TestCase):
    def test_units_and_rounding(self):
        data = {"hourly": [hourly.entry(NOW, 68.0, "Clear", "sunny", 10, 10.0, 359.6),
                           hourly.entry(NOW, 50.0, "Clear", "sunny", 0, 0.0, 90)]}
        metric = units.present(data, "metric")["hourly"]
        self.assertEqual((metric[0]["temperature"], metric[0]["wind_speed"], metric[0]["wind_direction"]), (20, 16, 0))
        # Calm has no direction
        self.assertIsNone(metric[1]["wind_direction"])
        self.assertEqual(units.present(data, "imperial")["hourly"][0]["temperature"], 68)

    def test_the_mock_has_a_day_of_hours(self):
        payload = u.build_mock_payload()
        self.assertEqual(len(payload["hourly"]), hourly.HOURS)
        self.assertEqual(set(payload["hourly"][0]), FIELDS)
        self.assertIsInstance(payload["hourly"][0]["temperature"], int)

    def test_an_error_file_has_no_hours(self):
        self.assertEqual(u.build_error_payload("down")["hourly"], [])
