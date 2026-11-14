"""Each weather service is asked no more often than it allows, whatever OUTPOST_UPDATE_INTERVAL is."""

import io
import json
import unittest
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
from providers import metno, nws, openmeteo, pirateweather

START = 1_800_000_000.0


class OpenMeteoTests(unittest.TestCase):
    def setUp(self):
        openmeteo._cache.clear()
        self.addCleanup(openmeteo._cache.clear)
        self.now = START
        mock.patch.object(openmeteo.time, "time", side_effect=lambda: self.now).start()
        self.urlopen = mock.patch("urllib.request.urlopen", side_effect=self.answer).start()
        self.addCleanup(mock.patch.stopall)

    def answer(self, request, timeout):
        return io.BytesIO(json.dumps(load_fixture("openmeteo.json")).encode())

    def test_the_same_answer_is_reused_for_15_minutes(self):
        self.assertEqual(openmeteo.MIN_REQUEST_SECONDS, 15 * 60)
        openmeteo.fetch(10.0, 20.0, "test")
        self.now += openmeteo.MIN_REQUEST_SECONDS - 1
        openmeteo.fetch(10.0, 20.0, "test")
        self.assertEqual(self.urlopen.call_count, 1)
        self.now += 1
        openmeteo.fetch(10.0, 20.0, "test")
        self.assertEqual(self.urlopen.call_count, 2)

    def test_each_place_has_its_own_answer(self):
        openmeteo.fetch(10.0, 20.0, "test")
        openmeteo.fetch(11.0, 20.0, "test")
        self.assertEqual(self.urlopen.call_count, 2)

    def test_a_failure_is_not_kept(self):
        self.urlopen.side_effect = OSError("down")
        with self.assertRaises(Exception):
            openmeteo.fetch_raw(10.0, 20.0, "test")
        self.urlopen.side_effect = self.answer
        openmeteo.fetch_raw(10.0, 20.0, "test")
        self.assertEqual(self.urlopen.call_count, 2)

    def test_changing_an_answer_does_not_change_the_kept_one(self):
        openmeteo.fetch_raw(10.0, 20.0, "test")["current"]["temperature_2m"] = -999
        self.assertNotEqual(openmeteo.fetch_raw(10.0, 20.0, "test")["current"]["temperature_2m"], -999)


class NwsTests(unittest.TestCase):
    def setUp(self):
        for cache in (nws._cache, nws._point_cache):
            cache.clear()
            self.addCleanup(cache.clear)
        self.now = START
        mock.patch.object(nws.time, "time", side_effect=lambda: self.now).start()
        self.get = mock.patch.object(nws, "_get", side_effect=self.answer).start()
        self.addCleanup(mock.patch.stopall)

    def answer(self, url, user_agent):
        if "/points/" in url:
            return load_fixture("nws_points.json")
        if url.endswith("/forecast"):
            return load_fixture("nws_forecast.json")
        if url.endswith("/stations"):
            return load_fixture("nws_stations.json")
        if "/observations/latest" in url:
            return {"properties": {}}  # no temperature: every station is tried
        if "/alerts/active" in url:
            return load_fixture("nws_alerts.json")
        raise AssertionError(url)

    def count(self, text):
        return sum(1 for call in self.get.call_args_list if text in call.args[0])

    def update_every_minute_for(self, minutes):
        for _ in range(minutes):
            nws.fetch(10.0, 20.0, "test")
            self.now += 60

    def test_forecast_every_15_minutes(self):
        self.update_every_minute_for(30)
        self.assertEqual(self.count("/forecast"), 2)

    def test_observations_every_5_minutes(self):
        self.update_every_minute_for(10)
        stations = len(load_fixture("nws_stations.json")["features"])
        self.assertEqual(self.count("/observations/latest"), 2 * min(stations, nws.STATIONS_TO_TRY))

    def test_alerts_every_minute(self):
        self.update_every_minute_for(3)
        self.assertEqual(self.count("/alerts/active"), 3)
        self.now -= 30
        nws.fetch_alerts(10.0, 20.0, "test")  # within the minute: reused
        self.assertEqual(self.count("/alerts/active"), 3)

    def test_a_failure_is_not_kept(self):
        self.get.side_effect = RuntimeError("NWS HTTP 503")
        with self.assertRaises(RuntimeError):
            nws._cached_get("https://api.weather.gov/x/forecast", "test", 900)
        self.get.side_effect = self.answer
        nws._cached_get("https://api.weather.gov/x/forecast", "test", 900)
        self.assertEqual(self.get.call_count, 2)


class IntervalTests(unittest.TestCase):
    def setUp(self):
        self.print = mock.patch("builtins.print").start()
        self.addCleanup(mock.patch.stopall)

    def test_too_short_an_interval_is_raised_to_a_minute(self):
        for seconds in (0, 5, 59):
            with self.subTest(seconds=seconds):
                self.assertEqual(u.update_interval_setting(seconds), 60)
        self.assertIn("too short", str(self.print.call_args))

    def test_longer_intervals_are_kept(self):
        for seconds in (60, 300, 1800):
            self.assertEqual(u.update_interval_setting(seconds), seconds)
        self.print.assert_not_called()

    def test_the_limits_are_reported_at_startup(self):
        with mock.patch.object(u, "UPDATE_INTERVAL", 60):
            text = u.request_limits_text()
        for part in ("Open-Meteo every 15 min", "NWS forecast every 15 min", "observations every 5 min",
                     "alerts every 1 min", "MET Norway", "Pirate Weather every 10 min"):
            self.assertIn(part, text)

    def test_a_longer_interval_is_what_is_reported(self):
        with mock.patch.object(u, "UPDATE_INTERVAL", 1800):
            self.assertIn("Open-Meteo every 30 min", u.request_limits_text())

    def test_services_that_already_had_minimums_keep_them(self):
        self.assertGreaterEqual(pirateweather.MIN_CACHE_SECONDS, 600)
        self.assertGreaterEqual(metno.MIN_CACHE_SECONDS, 60)


if __name__ == "__main__":
    unittest.main()
