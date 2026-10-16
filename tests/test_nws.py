import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers
from helpers import load_fixture
from providers import nws


def periods():
    return load_fixture("nws_forecast.json")["properties"]["periods"]


def observation(temp_c=28.9, age=timedelta(minutes=10)):
    obs = load_fixture("nws_observation.json")
    obs["properties"]["timestamp"] = (datetime.now(timezone.utc) - age).isoformat()
    obs["properties"]["temperature"]["value"] = temp_c
    return obs


class IconTests(unittest.TestCase):
    def test_wording_maps_to_icons(self):
        cases = {
            "Sunny": "sunny",
            "Mostly Sunny": "sunny",
            "Mostly Clear": "sunny",
            "Fair": "sunny",
            "Partly Cloudy": "partly-cloudy",
            "Partly Sunny": "partly-cloudy",
            "Mostly Cloudy": "cloudy",
            "Overcast": "cloudy",
            "Patchy Fog": "fog",
            "Haze": "fog",
            "Light Drizzle": "drizzle",
            "Chance Rain Showers": "rain",
            "Rain And Snow": "sleet",
            "Freezing Rain": "sleet",
            "Snow Showers": "snow",
            "Chance Showers And Thunderstorms": "storm",
            "Breezy": "wind",
            "Sunny And Breezy": "sunny",
            "Hot": "unknown",
            "": "unknown",
        }
        for text, icon in cases.items():
            with self.subTest(text=text):
                self.assertEqual(nws.icon_from_text(text), icon)

    def test_night_variants(self):
        self.assertEqual(nws.icon_from_text("Clear", is_day=False), "clear-night")
        self.assertEqual(nws.icon_from_text("Partly Cloudy", is_day=False), "partly-cloudy-night")
        self.assertEqual(nws.icon_from_text("Rain", is_day=False), "rain")


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.forecast = nws.build_forecast(periods())

    def test_five_calendar_days(self):
        self.assertEqual([d["day"] for d in self.forecast],
                         ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19"])

    def test_today_has_no_high_after_the_day_period_ends(self):
        today = self.forecast[0]
        self.assertIsNone(today["high_f"])
        self.assertEqual(today["low_f"], 62)
        self.assertEqual(today["icon"], "clear-night")

    def test_day_and_night_periods_are_merged(self):
        day = self.forecast[1]
        self.assertEqual((day["high_f"], day["low_f"]), (85, 60))
        self.assertEqual(day["condition"], "Sunny")

    def test_precipitation_uses_the_highest_chance_and_defaults_to_zero(self):
        self.assertEqual([d["precipitation_percent"] for d in self.forecast], [0, 10, 30, 0, 0])

    def test_icons(self):
        self.assertEqual([d["icon"] for d in self.forecast],
                         ["clear-night", "sunny", "storm", "cloudy", "wind"])

    def test_uv_is_not_provided(self):
        self.assertTrue(all(d["uv_index"] is None for d in self.forecast))


class CurrentTests(unittest.TestCase):
    def test_from_observation(self):
        current = nws.build_current(periods(), observation()["properties"])
        self.assertEqual(current["temperature_f"], 84)
        self.assertEqual(current["wind_mph"], 9)
        self.assertEqual(current["pressure_inhg"], 30.05)
        self.assertEqual(current["visibility_miles"], 10.0)
        self.assertEqual(current["humidity_percent"], 22)
        self.assertIsNone(current["uv_index"])
        self.assertEqual(current["condition"], "Fair")

    def test_icon_follows_day_or_night_of_the_first_period(self):
        # The first forecast period is "Tonight", so it is night
        self.assertEqual(nws.build_current(periods(), observation()["properties"])["icon"], "clear-night")
        day_periods = periods()
        day_periods[0]["isDaytime"] = True
        self.assertEqual(nws.build_current(day_periods, observation()["properties"])["icon"], "sunny")

    def test_heat_index_is_used_for_feels_like(self):
        obs = observation()["properties"]
        obs["heatIndex"]["value"] = 35.0
        self.assertEqual(nws.build_current(periods(), obs)["feels_like_f"], 95)

    def test_feels_like_defaults_to_temperature(self):
        self.assertEqual(nws.build_current(periods(), observation()["properties"])["feels_like_f"], 84)

    def test_falls_back_to_the_forecast_without_an_observation(self):
        current = nws.build_current(periods(), None)
        self.assertEqual(current["temperature_f"], 62)
        self.assertEqual(current["wind_mph"], 10)
        self.assertEqual(current["condition"], "Mostly Clear")
        self.assertIsNone(current["pressure_inhg"])
        self.assertIsNone(current["visibility_miles"])


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.alerts = nws.build_alerts(load_fixture("nws_alerts.json")["features"])

    def test_test_and_cancelled_messages_are_dropped(self):
        self.assertEqual([a["title"] for a in self.alerts], ["Red Flag Warning", "Heat Advisory"])

    def test_sorted_by_severity(self):
        self.assertEqual([a["severity"] for a in self.alerts], ["severe", "moderate"])

    def test_end_time_is_preferred_over_expiry(self):
        self.assertEqual(self.alerts[0]["expires"], "2026-07-16T03:30:00+00:00")
        self.assertEqual(self.alerts[1]["expires"], "2026-07-16T03:00:00+00:00")

    def test_fields(self):
        self.assertEqual(self.alerts[0]["description"], "Red Flag Warning until 9 PM")
        self.assertTrue(self.alerts[0]["uri"].startswith("https://"))

    def test_limit(self):
        many = [{"id": str(n), "properties": {"event": f"E{n}", "severity": "Minor", "status": "Actual"}} for n in range(20)]
        self.assertEqual(len(nws.build_alerts(many)), nws.MAX_ALERTS)

    def test_none_input(self):
        self.assertEqual(nws.build_alerts(None), [])


class NormalizeTests(unittest.TestCase):
    def test_empty_forecast_raises(self):
        with self.assertRaises(RuntimeError):
            nws.normalize([], None, [])


class FetchTests(unittest.TestCase):
    def setUp(self):
        nws._point_cache.clear()
        self.addCleanup(nws._point_cache.clear)
        self.calls = []
        self.user_agents = []
        self.observations = {"KAAA": {"properties": {"timestamp": datetime.now(timezone.utc).isoformat(),
                                                       "temperature": {"value": None}}},
                             "KBBB": observation(),
                             "KCCC": observation(20.0)}
        self.outside_us = False
        self.alerts_error = None
        patcher = mock.patch.object(nws, "_get", side_effect=self.fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_get(self, url, user_agent):
        self.calls.append(url)
        self.user_agents.append(user_agent)
        if "/points/" in url:
            if self.outside_us:
                raise nws._NotFound(url)
            return load_fixture("nws_points.json")
        if url.endswith("/forecast"):
            return load_fixture("nws_forecast.json")
        if url.endswith("/stations"):
            return load_fixture("nws_stations.json")
        if "/observations/latest" in url:
            return self.observations[url.split("/stations/")[1].split("/")[0]]
        if "/alerts/active" in url:
            if self.alerts_error:
                raise self.alerts_error
            return load_fixture("nws_alerts.json")
        raise AssertionError(f"unexpected URL {url}")

    def count(self, text):
        return sum(1 for call in self.calls if text in call)

    def test_full_fetch(self):
        data = nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertEqual(data["source"], nws.SOURCE)
        self.assertEqual(len(data["forecast"]), 5)
        self.assertEqual([a["title"] for a in data["alerts"]], ["Red Flag Warning", "Heat Advisory"])

    def test_skips_a_station_without_a_temperature(self):
        data = nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertEqual(data["current"]["temperature_f"], 84)  # from KBBB, not the forecast's 62

    def test_user_agent_is_sent_on_every_request(self):
        nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertTrue(all(ua == "Outpost-Test" for ua in self.user_agents))

    def test_location_lookup_is_cached(self):
        nws.fetch(10.0, 20.0, "Outpost-Test")
        nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertEqual(self.count("/points/"), 1)
        self.assertEqual(self.count("/stations") - self.count("/observations/latest"), 1)

    def test_stale_observations_fall_back_to_the_forecast(self):
        old = timedelta(hours=6)
        self.observations = {k: observation(age=old) for k in self.observations}
        data = nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertEqual(data["current"]["temperature_f"], 62)
        self.assertIsNone(data["current"]["pressure_inhg"])

    def test_failed_alert_lookup_fails_the_update(self):
        self.alerts_error = RuntimeError("NWS HTTP 503")
        with self.assertRaises(RuntimeError) as caught:
            nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertNotIsInstance(caught.exception, nws.NoCoverageError)

    def test_outside_the_us(self):
        self.outside_us = True
        with self.assertRaises(nws.NoCoverageError):
            nws.fetch(10.0, 20.0, "Outpost-Test")
        before = len(self.calls)
        with self.assertRaises(nws.NoCoverageError):
            nws.fetch(10.0, 20.0, "Outpost-Test")
        self.assertEqual(len(self.calls), before)  # the answer was cached


class HttpTests(unittest.TestCase):
    def http_error(self, code):
        return urllib.error.HTTPError("http://example.invalid", code, "x", {}, io.BytesIO(b""))

    def test_retries_temporary_server_errors(self):
        responses = [self.http_error(503), self.http_error(503), io.BytesIO(b'{"ok": true}')]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen, \
                mock.patch.object(nws.time, "sleep"):
            self.assertEqual(nws._get("http://example.invalid", "test"), {"ok": True})
        self.assertEqual(urlopen.call_count, 3)

    def test_gives_up_after_three_attempts(self):
        with mock.patch("urllib.request.urlopen", side_effect=self.http_error(500)) as urlopen, \
                mock.patch.object(nws.time, "sleep"):
            with self.assertRaises(RuntimeError):
                nws._get("http://example.invalid", "test")
        self.assertEqual(urlopen.call_count, nws.RETRIES)

    def test_not_found_is_not_retried(self):
        with mock.patch("urllib.request.urlopen", side_effect=self.http_error(404)) as urlopen:
            with self.assertRaises(nws._NotFound):
                nws._get("http://example.invalid", "test")
        self.assertEqual(urlopen.call_count, 1)

    def test_client_errors_are_not_retried(self):
        with mock.patch("urllib.request.urlopen", side_effect=self.http_error(403)) as urlopen:
            with self.assertRaises(RuntimeError):
                nws._get("http://example.invalid", "test")
        self.assertEqual(urlopen.call_count, 1)

    def test_sends_the_required_headers(self):
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b"{}")) as urlopen:
            nws._get("http://example.invalid", "Outpost-Test (test@example.com)")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header("User-agent"), "Outpost-Test (test@example.com)")
        self.assertEqual(request.get_header("Accept"), "application/geo+json")


if __name__ == "__main__":
    unittest.main()
