"""OpenWeatherMap provider (app/providers/openweathermap.py, One Call API 4.0), and how the updater uses it."""

import io
import json
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
import units
from providers import openweathermap as owm
from test_updater import UpdaterTestCase, openmeteo_data

NOW = datetime(2026, 11, 13, 20, 10, tzinfo=timezone.utc)  # the current record is from 20:00 UTC
KEY = "owm-secret-key-123"
WIND = "2.49.0.0.840.0.EX.1.wind"
STORM = "2.49.0.0.840.0.EX.2.storm"


def owm_raw():
    """What fetch_raw returns, from the fixture's three endpoint answers."""
    fixture = load_fixture("openweathermap.json")
    current = fixture["current"]
    return {"timezone": current["timezone"], "timezone_offset": current["timezone_offset"],
            "current": current["data"][0], "hourly": fixture["timeline/1h"]["data"],
            "daily": fixture["timeline/1day"]["data"]}


def owm_data():
    return owm.normalize(owm_raw(), now=NOW)


class NormalizeTests(unittest.TestCase):
    def test_capabilities(self):
        self.assertEqual(owm.CAPABILITIES, {"current", "forecast", "uv"})
        self.assertEqual(owm_data()["alerts"], [])
        self.assertEqual(owm_data()["source"], "OpenWeather")
        self.assertEqual(owm_data()["timezone"], "America/Chicago")

    def test_current(self):
        current = owm_data()["current"]
        self.assertEqual((current["temperature"], current["feels_like"], current["dew_point"]), (58.3, 56.9, 38.2))
        self.assertEqual((current["humidity"], current["wind_speed"], current["wind_gust"]), (47, 11.6, 20.3))
        self.assertEqual(current["wind_direction"], 210)
        self.assertEqual(current["uv_index"], 3)
        self.assertEqual((current["condition"], current["icon"]), ("Scattered clouds", "partly-cloudy"))
        self.assertEqual(current["observed_at"], "2026-11-13T20:00:00+00:00")
        shown = units.present({"current": current, "forecast": []}, "imperial")["current"]
        self.assertEqual(shown["pressure"], 29.92)  # 1013.2 hPa
        self.assertEqual(shown["visibility"], 6.2)  # 10,000 metres
        metric = units.present({"current": current, "forecast": []}, "metric")["current"]
        self.assertEqual(metric["visibility"], 10.0)

    def test_forecast(self):
        forecast = owm_data()["forecast"]
        self.assertEqual([day["day"] for day in forecast],
                         ["2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17"])  # 5 of 6
        self.assertEqual((forecast[0]["high"], forecast[0]["low"]), (61.7, 39.6))
        self.assertEqual([day["precipitation_chance"] for day in forecast], [5, 90, 62, 48, 0])
        self.assertEqual([day["icon"] for day in forecast], ["partly-cloudy", "rain", "storm", "snow", "sunny"])
        self.assertEqual([day["uv_index"] for day in forecast], [3, 1, 2, 1, 4])
        # A long description gives way to the code's own text
        self.assertEqual(forecast[2]["condition"], "Thunderstorms")
        self.assertEqual(forecast[1]["condition"], "Moderate rain")

    def test_daily_amounts_in_either_form(self):
        amounts = [day["precipitation"] and round(day["precipitation"], 3) for day in owm_data()["forecast"]]
        # 6.35 mm for the day; {"1h": 0.1058} mm/h on average (2.54 mm); 5.08 mm of snow as water
        self.assertEqual(amounts, [None, 0.25, 0.1, 0.2, None])
        self.assertIsNone(owm._day_amount({"1h": "x"}))

    def test_hourly(self):
        hourly = owm_data()["hourly"]
        self.assertEqual([hour["time"][11:16] for hour in hourly], ["20:00", "21:00", "22:00", "23:00"])
        self.assertEqual([hour["precipitation_chance"] for hour in hourly], [5, 40, 60, 0])
        self.assertEqual([hour["icon"] for hour in hourly], ["partly-cloudy", "rain", "sleet", "clear-night"])
        self.assertEqual([hour["precipitation"] and round(hour["precipitation"], 3) for hour in hourly],
                         [None, 0.03, 0.1, None])  # millimetres of rain and snow together, in inches
        self.assertEqual((hourly[1]["wind_speed"], hourly[1]["wind_direction"]), (12.0, 220))
        # Hours that have ended are left out
        later = owm.normalize(owm_raw(), now=datetime(2026, 11, 13, 23, 30, tzinfo=timezone.utc))
        self.assertEqual(len(later["hourly"]), 1)
        self.assertEqual(owm.build_hourly(None, NOW), [])

    def test_days_follow_the_locations_time_zone(self):
        raw = owm_raw()
        raw["timezone"] = "Not/AZone"
        raw["timezone_offset"] = 14 * 3600  # midday in Chicago is the next morning at UTC+14
        self.assertEqual(owm.normalize(raw, now=NOW)["forecast"][0]["day"], "2026-11-14")

    def test_conditions(self):
        cases = {
            (211, "11d"): "storm", (301, "09d"): "drizzle", (511, "13d"): "sleet", (502, "10n"): "rain",
            (611, "13d"): "sleet", (602, "13n"): "snow", (741, "50d"): "fog", (771, "50d"): "wind",
            (781, "50d"): "storm", (800, "01d"): "sunny", (800, "01n"): "clear-night",
            (801, "02n"): "partly-cloudy-night", (804, "04d"): "cloudy", (999, "01d"): "unknown",
        }
        for (code, icon), expected in cases.items():
            with self.subTest(code=code, icon=icon):
                self.assertEqual(owm.describe([{"id": code, "icon": icon}])[1], expected)
        for weather in (None, [], ["junk"], [{"id": "800"}], [{"id": True}]):
            with self.subTest(weather=weather):
                self.assertEqual(owm.describe(weather), ("Unknown", "unknown"))

    def test_missing_fields_are_none(self):
        raw = {"current": {}, "daily": [{"dt": 1794592800}, {"junk": 1}, "junk"]}
        data = owm.normalize(raw, now=NOW)
        self.assertTrue(all(value is None for key, value in data["current"].items() if key not in ("condition", "icon")))
        self.assertEqual(len(data["forecast"]), 1)
        self.assertIsNone(data["forecast"][0]["high"])
        self.assertEqual(data["hourly"], [])
        self.assertIsNone(data["timezone"])

    def test_missing_data_is_an_error(self):
        for raw in (None, {}, {"current": {}}, {"current": {}, "daily": []}, {"daily": [{}]},
                    {"current": None, "daily": [{}]}):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                owm.normalize(raw)


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class RequestTestCase(unittest.TestCase):
    """Answers each endpoint from the fixture, or with the errors in self.errors (by endpoint, or "*")."""

    def setUp(self):
        owm._cache.clear()
        self.addCleanup(owm._cache.clear)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(owm, "_blocked_until", 0.0).start()
        mock.patch.object(owm, "_blocked_reason", "").start()
        mock.patch.object(owm, "_calls", {"day": "", "calls": 0}).start()
        self.fixture = load_fixture("openweathermap.json")
        self.requests = []
        self.errors = {}
        self.clock = NOW.timestamp()
        mock.patch.object(owm.time, "time", side_effect=lambda: self.clock).start()
        mock.patch.object(owm.urllib.request, "urlopen", side_effect=self.urlopen).start()

    def endpoint(self, request):
        path = urllib.parse.urlsplit(request.full_url).path
        return urllib.parse.unquote(path[len("/data/4.0/onecall/"):])

    def urlopen(self, request, timeout):
        self.requests.append(request)
        endpoint = self.endpoint(request)
        errors = self.errors.get(endpoint) or self.errors.get("*")
        if errors:
            raise errors.pop(0)
        if endpoint.startswith("alert/"):
            return FakeResponse(self.fixture["alerts"][endpoint[len("alert/"):]])
        return FakeResponse(self.fixture[endpoint])

    def asked(self):
        return [self.endpoint(request) for request in self.requests]

    def http_error(self, code, reason="Error"):
        return urllib.error.HTTPError(f"{owm.API_URL}/current?appid={KEY}", code, reason, {}, None)


class RequestTests(RequestTestCase):
    def test_the_requests(self):
        raw = owm.fetch_raw(39.123456, -98.5, KEY, "Outpost/1")
        self.assertEqual(self.asked(), ["current", "timeline/1h", "timeline/1day"])
        for request in self.requests:
            url = request.full_url
            self.assertTrue(url.startswith(owm.API_URL + "/"))
            for part in ("lat=39.1235", "lon=-98.5000", "units=imperial", f"appid={KEY}"):
                self.assertIn(part, url)
            self.assertEqual(request.get_header("User-agent"), "Outpost/1")
        self.assertEqual(raw["timezone"], "America/Chicago")
        self.assertEqual(raw["current"]["dt"], 1794600000)
        self.assertEqual((len(raw["hourly"]), len(raw["daily"])), (4, 6))
        # The cache is keyed without the key
        self.assertNotIn(KEY, repr(owm._cache.keys()))

    def test_each_endpoint_is_kept_for_its_own_time(self):
        owm.fetch_raw(1, 2, KEY, "ua")
        self.clock += 601
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(self.asked()[3:], ["current"])
        self.clock += 1200  # 30 minutes in
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(self.asked()[4:], ["current", "timeline/1h"])
        self.clock += 1800  # an hour in
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(self.asked()[6:], ["current", "timeline/1h", "timeline/1day"])

    def test_one_minute_updates_stay_well_inside_the_free_calls(self):
        for _ in range(24 * 60):
            owm.fetch_raw(1, 2, KEY, "ua")
            owm.fetch_alerts(1, 2, KEY, "ua")
            self.clock += 60
        # 144 + 48 + 24, and each of the two alerts asked about a few times a day at most
        self.assertLessEqual(len(self.requests), 240)
        self.assertLess(len(self.requests), owm.DAILY_CALL_LIMIT)

    def test_never_more_than_the_daily_limit(self):
        self.clock = datetime(2026, 11, 13, 12, tzinfo=timezone.utc).timestamp()
        owm._calls.update({"day": "2026-11-13", "calls": owm.DAILY_CALL_LIMIT})
        with self.assertRaisesRegex(RuntimeError, "midnight UTC"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(self.requests, [])
        # A new UTC day starts again
        self.clock = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc).timestamp()
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(owm.calls_today(self.clock), 3)
        self.assertLess(owm.DAILY_CALL_LIMIT, 1000)

    def test_without_a_key_nothing_is_sent(self):
        for fetch in (owm.fetch_raw, owm.fetch_alerts):
            with self.subTest(fetch=fetch.__name__), \
                    self.assertRaisesRegex(RuntimeError, "OUTPOST_OPENWEATHERMAP_API_KEY"):
                fetch(1, 2, "", "ua")
        self.assertEqual(self.requests, [])

    def test_errors_never_show_the_key_or_the_address(self):
        errors = [self.http_error(401, "Unauthorized"), self.http_error(429, "Too Many"),
                  self.http_error(500, f"Server error for {owm.API_URL}?appid={KEY}"),
                  urllib.error.URLError(f"failed {owm.API_URL}?appid={KEY}"), urllib.error.URLError(OSError("no route")),
                  TimeoutError("timed out")]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                owm._cache.clear()
                owm._blocked_until = 0.0
                self.errors = {"*": [error]}
                with self.assertRaises(RuntimeError) as caught:
                    owm.fetch_raw(1, 2, KEY, "ua")
                self.assertNotIn(KEY, str(caught.exception))
                self.assertNotIn("appid", str(caught.exception))
                # Not chained, so a printed traceback can't show the address either
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)

    def test_a_refused_key_is_not_tried_again_for_ten_minutes(self):
        self.errors = {"current": [self.http_error(401, "Unauthorized")]}
        with self.assertRaisesRegex(RuntimeError, "OUTPOST_OPENWEATHERMAP_API_KEY"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.clock += 540
        with self.assertRaisesRegex(RuntimeError, "refused"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 61
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 4)

    def test_too_many_requests_backs_off(self):
        self.errors = {"timeline/1h": [self.http_error(429, "Too Many")]}
        with self.assertRaisesRegex(RuntimeError, "429"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.clock += 3500
        with self.assertRaisesRegex(RuntimeError, "too many"):
            owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(len(self.requests), 2)  # nothing asked while waiting
        self.clock += 101
        owm.fetch_raw(1, 2, KEY, "ua")
        self.assertEqual(self.asked()[2:], ["current", "timeline/1h", "timeline/1day"])

    def test_invalid_answers(self):
        mock.patch.object(owm.urllib.request, "urlopen", return_value=FakeResponse(b"not json")).start()
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            owm.fetch_raw(1, 2, KEY, "ua")
        mock.patch.object(owm.urllib.request, "urlopen", return_value=FakeResponse([1, 2])).start()
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            owm.fetch_raw(1, 2, KEY, "ua")


class AlertTests(RequestTestCase):
    def test_ids_from_the_current_conditions_and_the_hours(self):
        self.assertEqual(owm.alert_ids(owm_raw()), [WIND, STORM])
        for raw in (None, {}, {"current": {"alerts": None}},
                    {"current": {"alerts": [5, "", None]}, "hourly": ["junk"]}):
            with self.subTest(raw=raw):
                self.assertEqual(owm.alert_ids(raw), [])

    def test_alerts_most_serious_first(self):
        alerts = owm.fetch_alerts(1, 2, KEY, "ua")
        self.assertEqual([a["title"] for a in alerts], ["Winter Storm Warning", "Wind Advisory"])
        wind = alerts[1]
        self.assertEqual(wind["severity"], "minor")
        # English when there is a choice
        self.assertEqual(wind["description"], "South winds 25 to 35 mph with gusts up to 50 mph.")
        self.assertEqual(wind["onset"], "2026-11-13T20:00:00+00:00")
        self.assertEqual(wind["expires"], "2026-11-14T02:00:00+00:00")
        self.assertIsNone(wind["uri"])
        # Alerts alone don't ask for the daily timeline; each alert is asked about once
        self.assertEqual(self.asked(), ["current", "timeline/1h", f"alert/{WIND}", f"alert/{STORM}"])

    def test_alert_details_are_kept_until_they_end(self):
        owm.fetch_alerts(1, 2, KEY, "ua")
        self.clock += 3 * 3600  # the wind advisory ends 6 hours after it starts
        owm.fetch_alerts(1, 2, KEY, "ua")
        self.assertNotIn(f"alert/{WIND}", self.asked()[4:])
        self.clock += 4 * 3600
        owm.fetch_alerts(1, 2, KEY, "ua")
        self.assertIn(f"alert/{WIND}", self.asked()[4:])

    def test_weather_and_alerts_share_calls(self):
        owm.fetch(1, 2, KEY, "ua")
        owm.fetch_alerts(1, 2, KEY, "ua")
        self.assertEqual(self.asked().count("current"), 1)
        self.assertEqual(self.asked().count("timeline/1h"), 1)

    def test_a_failed_alert_fails_the_lookup(self):
        self.errors = {f"alert/{STORM}": [self.http_error(500)]}
        with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
            owm.fetch_alerts(1, 2, KEY, "ua")

    def test_alert_fields(self):
        alert = owm.build_alert({"event": "", "tags": ["Thunderstorm"],
                                 "description": [{"language": "fr-FR", "description": "Orages."}]})
        self.assertEqual((alert["title"], alert["description"], alert["severity"]),
                         ("Thunderstorm", "Orages.", "unknown"))
        self.assertEqual((alert["onset"], alert["expires"]), (None, None))
        self.assertEqual(owm.build_alert({})["title"], "Weather alert")
        self.assertEqual(owm.build_alert({"description": "Plain  text"})["description"], "Plain text")
        self.assertEqual(owm.build_alert({"description": [{"language": "en", "description": ""}, "junk"]})["description"], "")

    def test_severity_from_the_event_name(self):
        cases = {"Red Wind Warning": "extreme", "Extreme Heat Warning": "extreme",
                 "Orange Rain Warning": "severe", "Amber warning for snow": "severe",
                 "Yellow Thunderstorm Warning": "moderate", "Flood Warning": "severe",
                 "Winter Storm Watch": "moderate", "Wind Advisory": "minor",
                 "Special Weather Statement": "minor", "Avis de gel": "unknown", "": "unknown",
                 "Frost": "unknown", "Red-flag": "extreme"}
        for event, expected in cases.items():
            with self.subTest(event=event):
                self.assertEqual(owm.severity(event), expected)

    def test_repeats_dropped_and_at_most_five(self):
        same = {"event": "Frost", "end": 1794621600, "description": "Cold."}
        self.assertEqual(len(owm.build_alerts([same, dict(same), "junk"])), 1)
        self.assertEqual(owm.build_alerts(None), [])
        many = [{"event": f"Alert {n}"} for n in range(9)]
        self.assertEqual(len(owm.build_alerts(many)), owm.MAX_ALERTS)


class UpdaterTests(UpdaterTestCase):
    ALERTS = [{"title": "Storm Warning", "description": "", "severity": "severe", "onset": None,
               "expires": None, "uri": None}]

    def setUp(self):
        super().setUp()
        self.owm_alerts.return_value = self.ALERTS

    def run_update(self, key=KEY, provider="openweathermap", alerts_provider="auto", location=None, state=None):
        with mock.patch.object(u, "PROVIDER", provider), mock.patch.object(u, "ALERTS_PROVIDER", alerts_provider), \
                mock.patch.object(u, "OPENWEATHERMAP_API_KEY", key), \
                mock.patch.object(u, "THEMES_DIR", helpers.ROOT / "web" / "themes"), \
                mock.patch.object(u, "CONFIG_PATH", self.data_dir / "config.json", create=True), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()), \
                mock.patch.object(u.openweathermap, "fetch", return_value=owm_data()) as fetch:
            result = u.update_once(location, state) if location else u.update_once()
        return (result if location else self.output()), fetch

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)

    def test_openweathermap(self):
        data, fetch = self.run_update()
        fetch.assert_called_once_with(u.LATITUDE, u.LONGITUDE, KEY, u.USER_AGENT)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sources"]["weather"], {"id": "openweathermap", "name": "OpenWeather"})
        self.assertEqual(data["timezone"], "America/Chicago")

    def test_outside_the_us_its_own_alerts_are_used(self):
        data, _ = self.run_update()
        self.owm_alerts.assert_called_once()
        self.assertEqual(data["sources"]["alerts"], {"id": "openweathermap", "name": "OpenWeather"})
        self.assertEqual(data["alerts"], self.ALERTS)

    def test_in_the_us_nws_alerts_come_first(self):
        self.nws_alerts.side_effect = None
        self.nws_alerts.return_value = []
        data, _ = self.run_update()
        self.owm_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")

    def test_other_weather_providers_never_use_its_alerts_under_auto(self):
        data, _ = self.run_update(provider="openmeteo")
        self.owm_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_it_can_be_chosen_for_alerts(self):
        self.nws_alerts.side_effect = None
        data, _ = self.run_update(provider="openmeteo", alerts_provider="openweathermap")
        self.nws_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "openweathermap")

    def test_choosing_it_for_alerts_without_a_key_warns_once(self):
        self.run_update(key="", provider="openmeteo", alerts_provider="openweathermap")
        data, _ = self.run_update(key="", provider="openmeteo", alerts_provider="openweathermap")
        self.owm_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(self.printed().count("needs OUTPOST_OPENWEATHERMAP_API_KEY"), 1)

    def test_the_setting_is_known(self):
        self.assertEqual(u.alerts_provider_setting("OpenWeatherMap"), "openweathermap")

    def test_other_places_never_use_the_key(self):
        elsewhere = u.Location(50.0, 10.0, "Fictional Town")
        self.assertEqual(u.openweathermap_key(elsewhere), "")
        data, fetch = self.run_update(location=elsewhere, state=u.LocationState())
        fetch.assert_not_called()
        self.owm_alerts.assert_not_called()
        self.assertEqual(data["sources"]["weather"]["id"], "openmeteo")
        data, _ = self.run_update(provider="openmeteo", alerts_provider="openweathermap", location=elsewhere,
                                  state=u.LocationState())
        self.owm_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_never_part_of_auto(self):
        with mock.patch.object(u, "OPENWEATHERMAP_API_KEY", KEY), mock.patch.object(u, "PIRATEWEATHER_API_KEY", ""), \
                mock.patch.object(u, "PROVIDER", "auto"), \
                mock.patch.object(u.nws, "fetch", side_effect=u.nws.NoCoverageError("US only")), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()), \
                mock.patch.object(u.openweathermap, "fetch") as fetch:
            u.update_once()
        fetch.assert_not_called()
        self.owm_alerts.assert_not_called()
        self.assertEqual(self.output()["sources"]["weather"]["id"], "openmeteo")

    def test_the_key_is_never_written_out(self):
        self.run_update()
        for path in self.data_dir.iterdir():
            with self.subTest(file=path.name):
                self.assertNotIn(KEY, path.read_text(encoding="utf-8"))
        self.assertNotIn(KEY, self.printed())

    def test_a_failure_keeps_the_last_good_data(self):
        self.run_update()
        with mock.patch.object(u, "PROVIDER", "openweathermap"), mock.patch.object(u, "OPENWEATHERMAP_API_KEY", KEY), \
                mock.patch.object(u.openweathermap, "fetch", side_effect=RuntimeError("OpenWeatherMap HTTP 500")):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["last_error"], "OpenWeatherMap HTTP 500")
        self.assertEqual(data["sources"]["weather"]["id"], "openweathermap")

    def test_request_limits_are_listed(self):
        self.assertIn("OpenWeatherMap current conditions every 10 min, hours every 30 min, days every 60 min "
                      "(at most 900 calls a day)", u.request_limits_text())


if __name__ == "__main__":
    unittest.main()
