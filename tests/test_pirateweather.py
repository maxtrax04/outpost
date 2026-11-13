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
        mock.patch.object(pirateweather, "_blocked_reason", "").start()
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

    def test_a_refused_key_is_not_tried_again_for_ten_minutes(self):
        self.responses = [urllib.error.HTTPError("u", 401, "Unauthorized", headers(), None), self.ok()]
        with self.assertRaisesRegex(RuntimeError, "refused"):
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.clock += 540
        with self.assertRaisesRegex(RuntimeError, "OUTPOST_PIRATEWEATHER_API_KEY"):
            pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 61
        pirateweather.fetch_raw(1, 2, self.KEY, "ua")
        self.assertEqual(len(self.requests), 2)

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

    OSLO = (59.91, 10.75)
    KANSAS = (39.0, -98.0)
    PARIS = (48.85, 2.35)

    def run_auto(self, key, place, pirate=None, metno=None, nws_fetch=None):
        latitude, longitude = place
        outside_us = {"side_effect": nws.NoCoverageError("US only")}
        with mock.patch.object(u, "PROVIDER", "auto"), mock.patch.object(u, "PIRATEWEATHER_API_KEY", key), \
                mock.patch.object(u, "LATITUDE", latitude), mock.patch.object(u, "LONGITUDE", longitude), \
                mock.patch.object(u.pirateweather, "fetch", **(pirate or {"return_value": pirate_data()})) as pirate_fetch, \
                mock.patch.object(u.metno, "fetch", **(metno or {"return_value": metno_data()})), \
                mock.patch.object(u.nws, "fetch", **(nws_fetch or ({"return_value": nws_data()} if place == self.KANSAS
                                                                   else outside_us))), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        return self.output(), pirate_fetch

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)

    def test_regional_specialists_come_first_even_with_a_key(self):
        for place, expected in ((self.OSLO, "metno"), (self.KANSAS, "nws")):
            with self.subTest(expected=expected):
                data, pirate_fetch = self.run_auto("k", place)
                pirate_fetch.assert_not_called()
                self.assertEqual(data["sources"]["weather"]["id"], expected)

    def test_elsewhere_a_key_means_pirate_weather_instead_of_open_meteo(self):
        data, _ = self.run_auto("k", self.PARIS)
        self.assertEqual(data["sources"]["weather"]["id"], "pirateweather")
        data, pirate_fetch = self.run_auto("", self.PARIS)
        pirate_fetch.assert_not_called()
        self.assertEqual(data["sources"]["weather"]["id"], "openmeteo")

    def test_pirate_weather_takes_over_when_a_specialist_fails(self):
        data, _ = self.run_auto("k", self.OSLO, metno={"side_effect": RuntimeError("MET Norway HTTP 503")})
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "pirateweather"))
        self.assertIn("MET Norway failed", self.printed())
        data, _ = self.run_auto("k", self.KANSAS, nws_fetch={"side_effect": RuntimeError("NWS HTTP 503")})
        self.assertEqual(data["sources"]["weather"]["id"], "pirateweather")

    def test_without_a_key_a_specialist_failure_keeps_the_last_good_data(self):
        self.run_auto("", self.OSLO)
        data, _ = self.run_auto("", self.OSLO, metno={"side_effect": RuntimeError("MET Norway HTTP 503")})
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["last_error"], "MET Norway HTTP 503")

    def test_when_both_fail_the_specialists_error_is_reported(self):
        self.run_auto("k", self.OSLO)
        data, _ = self.run_auto("k", self.OSLO, metno={"side_effect": RuntimeError("MET Norway HTTP 503")},
                                pirate={"side_effect": RuntimeError("Pirate Weather HTTP 500")})
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["last_error"], "MET Norway HTTP 503")

    def test_elsewhere_a_pirate_weather_failure_falls_back_to_open_meteo(self):
        data, _ = self.run_auto("k", self.PARIS, pirate={"side_effect": RuntimeError("Pirate Weather HTTP 500")})
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "openmeteo"))
        self.assertIn("Pirate Weather failed", self.printed())

    def test_in_the_us_alerts_stay_with_nws(self):
        data, _ = self.run_auto("k", self.KANSAS)
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.alerts = pirateweather.build_alerts(load_fixture("pirateweather.json"))

    def test_most_serious_first_and_repeats_dropped(self):
        self.assertEqual([a["title"] for a in self.alerts], ["Tornado Warning", "Wind Advisory", "Avis de gel"])

    def test_fields(self):
        wind = self.alerts[1]
        self.assertEqual(wind["severity"], "moderate")
        self.assertEqual(wind["description"], "South winds 25 to 35 mph with gusts up to 50 mph.")
        self.assertEqual(wind["expires"], "2026-11-14T02:00:00+00:00")
        self.assertEqual(wind["uri"], "https://alerts.example.gov/wind")

    def test_blank_severity_missing_end_and_bad_links(self):
        frost = self.alerts[2]
        self.assertEqual(frost["severity"], "unknown")
        self.assertIsNone(frost["expires"])  # -999
        self.assertIsNone(frost["uri"])
        self.assertEqual(frost["title"], "Avis de gel")  # kept in the publisher's language

    def test_no_alerts(self):
        for raw in ({}, {"alerts": None}, {"alerts": []}, {"alerts": ["junk"]}):
            with self.subTest(raw=raw):
                self.assertEqual(pirateweather.build_alerts(raw), [])

    def test_at_most_five(self):
        many = {"alerts": [{"title": f"Alert {n}", "severity": "Minor", "expires": -999} for n in range(9)]}
        self.assertEqual(len(pirateweather.build_alerts(many)), pirateweather.MAX_ALERTS)

    def test_the_forecast_request_includes_alerts(self):
        with mock.patch.object(pirateweather.urllib.request, "urlopen") as urlopen:
            urlopen.return_value = FakeResponse(load_fixture("pirateweather.json"), headers())
            pirateweather._cache.clear()
            self.addCleanup(pirateweather._cache.clear)
            with mock.patch.object(pirateweather, "_blocked_until", 0.0):
                pirateweather.fetch_alerts(1, 2, "k", "ua")
                pirateweather.fetch(1, 2, "k", "ua")
        self.assertEqual(urlopen.call_count, 1)  # the weather and the alerts share one call
        self.assertIn("exclude=minutely%2Chourly", urlopen.call_args[0][0].full_url)
        self.assertNotIn("alerts", urlopen.call_args[0][0].full_url)


class AlertOrderTests(UpdaterTestCase):
    PIRATE_ALERTS = [{"title": "Storm Warning", "description": "", "severity": "severe", "expires": None, "uri": None}]
    NWS_ALERTS = [{"title": "Flood Watch", "description": "", "severity": "moderate", "expires": None, "uri": None}]

    def run_update(self, provider="openmeteo", alerts_provider="auto", key="k", latitude=48.85, longitude=2.35):
        self.pirate_alerts.return_value = self.PIRATE_ALERTS
        with mock.patch.object(u, "PROVIDER", provider), mock.patch.object(u, "ALERTS_PROVIDER", alerts_provider), \
                mock.patch.object(u, "PIRATEWEATHER_API_KEY", key), \
                mock.patch.object(u, "LATITUDE", latitude), mock.patch.object(u, "LONGITUDE", longitude), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()), \
                mock.patch.object(u.metno, "fetch", return_value=metno_data()), \
                mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.pirateweather, "fetch", return_value=pirate_data()):
            u.update_once()
        return self.output()

    def in_the_us(self):
        self.nws_alerts.side_effect = None
        self.nws_alerts.return_value = self.NWS_ALERTS

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)

    def test_outside_the_us_auto_uses_pirate_weather_alerts_with_a_key(self):
        data = self.run_update()
        self.assertEqual(data["sources"]["alerts"], {"id": "pirateweather", "name": "Pirate Weather"})
        self.assertEqual(data["alerts"], self.PIRATE_ALERTS)

    def test_without_a_key_outside_the_us_there_are_none(self):
        data = self.run_update(key="")
        self.pirate_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_in_the_us_nws_comes_first(self):
        self.in_the_us()
        data = self.run_update(provider="pirateweather")
        self.pirate_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")
        self.assertEqual(data["alerts"], self.NWS_ALERTS)

    def test_nws_weather_keeps_its_own_alerts(self):
        data = self.run_update(provider="nws")
        self.pirate_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")

    def test_nordic_locations_outside_norway_get_pirate_weather_alerts_without_asking_nws(self):
        data = self.run_update(provider="metno", latitude=59.33, longitude=18.07)  # Stockholm
        self.nws_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "pirateweather")

    def test_norway_gets_met_norway_warnings_before_pirate_weather(self):
        data = self.run_update(provider="metno", latitude=59.91, longitude=10.75)  # Oslo
        self.nws_alerts.assert_not_called()
        self.pirate_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "metno")

    def test_pirateweather_can_be_chosen_anywhere(self):
        self.in_the_us()
        data = self.run_update(provider="nws", alerts_provider="pirateweather")
        self.nws_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "pirateweather")

    def test_choosing_pirateweather_without_a_key_warns_once(self):
        self.run_update(alerts_provider="pirateweather", key="")
        data = self.run_update(alerts_provider="pirateweather", key="")
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(self.printed().count("needs OUTPOST_PIRATEWEATHER_API_KEY"), 1)

    def test_a_failed_pirate_weather_alerts_lookup_keeps_the_last_ones(self):
        self.run_update()
        self.pirate_alerts.side_effect = RuntimeError("Pirate Weather HTTP 500")
        data = self.run_update()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["alerts"], self.PIRATE_ALERTS)
        self.assertIsNotNone(data["current"]["temperature"])


if __name__ == "__main__":
    unittest.main()
