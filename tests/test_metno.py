"""MET Norway provider (app/providers/metno.py)."""

import email.message
import io
import json
import os
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

import helpers
from helpers import load_fixture

import units
from providers import metno

OSLO = ZoneInfo("Europe/Oslo")
NOW = datetime(2026, 11, 13, 1, 30, tzinfo=timezone.utc)


def normalized(now=NOW, zone=OSLO):
    return metno.normalize(load_fixture("metno.json"), now=now, zone=zone)


class SymbolTests(unittest.TestCase):
    def test_symbols(self):
        cases = {
            "clearsky_day": ("Clear sky", "sunny"),
            "clearsky_night": ("Clear sky", "clear-night"),
            "fair_polartwilight": ("Fair", "sunny"),
            "partlycloudy_night": ("Partly cloudy", "partly-cloudy-night"),
            "cloudy": ("Cloudy", "cloudy"),
            "fog": ("Fog", "fog"),
            "lightrain": ("Light rain", "drizzle"),
            "rain": ("Rain", "rain"),
            "heavyrainshowers_day": ("Heavy rain showers", "rain"),
            "lightrainshowers_night": ("Light rain showers", "rain"),
            "sleet": ("Sleet", "sleet"),
            "lightsleetshowersandthunder_day": ("Light sleet showers and thunder", "storm"),
            "heavysnow": ("Heavy snow", "snow"),
            "snowshowers_polartwilight": ("Snow showers", "snow"),
            "rainandthunder": ("Rain and thunder", "storm"),
        }
        for symbol, expected in cases.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(metno.describe(symbol), expected)

    def test_unknown_symbols(self):
        for symbol in (None, "", "hail", "lightfoo_day"):
            with self.subTest(symbol=symbol):
                self.assertEqual(metno.describe(symbol), ("Unknown", "unknown"))

    def test_every_symbol_in_the_fixture_is_known(self):
        for entry in load_fixture("metno.json")["properties"]["timeseries"]:
            for block in ("next_1_hours", "next_6_hours", "next_12_hours"):
                symbol = ((entry["data"].get(block) or {}).get("summary") or {}).get("symbol_code")
                if symbol:
                    self.assertNotEqual(metno.describe(symbol)[1], "unknown", symbol)


class NormalizeTests(unittest.TestCase):
    def test_capabilities(self):
        self.assertEqual(metno.CAPABILITIES, {"current", "forecast", "uv"})
        self.assertEqual(normalized()["alerts"], [])
        self.assertEqual(normalized()["source"], "MET Norway (met.no)")

    def test_current_is_this_hours_forecast(self):
        current = normalized()["current"]
        # In the fixture: -1.6 °C, 81.8 %, 1.2 m/s, 989.1 hPa, fair_night
        shown = units.present({"current": current, "forecast": []}, "metric")["current"]
        self.assertEqual((shown["temperature"], shown["feels_like"], shown["wind_speed"], shown["pressure"]),
                         (-2, -2, 4, 989))
        self.assertEqual(current["humidity"], 82)
        self.assertEqual((current["condition"], current["icon"]), ("Fair", "clear-night"))
        self.assertIsNone(current["visibility"])
        self.assertEqual(current["uv_index"], 0)

    def test_current_follows_the_clock(self):
        later = normalized(now=NOW + timedelta(hours=5))["current"]
        entry = load_fixture("metno.json")["properties"]["timeseries"][5]
        self.assertEqual(later["temperature"], metno.C_TO_F(entry["data"]["instant"]["details"]["air_temperature"]))

    def test_before_the_first_entry_uses_the_first(self):
        early = normalized(now=NOW - timedelta(days=1))["current"]
        self.assertEqual(early["temperature"], normalized()["current"]["temperature"])

    def test_forecast_days(self):
        forecast = normalized()["forecast"]
        self.assertEqual([day["day"] for day in forecast],
                         ["2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17"])
        for day in forecast:
            with self.subTest(day=day["day"]):
                self.assertLessEqual(day["low"], day["high"])
                self.assertTrue(0 <= day["precipitation_chance"] <= 100)
                self.assertNotEqual(day["icon"], "unknown")
        self.assertEqual((forecast[2]["condition"], forecast[2]["precipitation_chance"]), ("Cloudy", 82))
        self.assertEqual(forecast[3]["icon"], "drizzle")

    def test_days_follow_the_time_zone(self):
        # Far west of UTC, 01:30 UTC is still the 12th; far east it is already the afternoon of the 13th
        self.assertEqual(normalized(zone=timezone(timedelta(hours=-10)))["forecast"][0]["day"], "2026-11-12")
        self.assertEqual(normalized(zone=timezone(timedelta(hours=13)))["forecast"][0]["day"], "2026-11-13")

    def test_no_forecast_is_an_error(self):
        with self.assertRaises(RuntimeError):
            metno.normalize({"properties": {"timeseries": []}})

    def test_every_reading_is_present(self):
        current = normalized()["current"]
        self.assertEqual(set(current), {"temperature", "feels_like", "condition", "icon", "humidity",
                                        "wind_speed", "wind_gust", "pressure", "uv_index", "visibility"})


class ZoneTests(unittest.TestCase):
    def test_the_tz_setting_is_used(self):
        with mock.patch.dict(os.environ, {"TZ": "Europe/Oslo"}):
            self.assertEqual(metno.local_zone(-120.0), ZoneInfo("Europe/Oslo"))

    def test_without_tz_the_longitude_decides(self):
        with mock.patch.dict(os.environ, {"TZ": ""}):
            self.assertEqual(metno.local_zone(10.7), timezone(timedelta(hours=1)))
            self.assertEqual(metno.local_zone(-118.2), timezone(timedelta(hours=-8)))

    def test_an_unknown_tz_falls_back_to_the_longitude(self):
        with mock.patch.dict(os.environ, {"TZ": "Not/AZone"}):
            self.assertEqual(metno.local_zone(30.0), timezone(timedelta(hours=2)))


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


class CacheTests(unittest.TestCase):
    """MET Norway's terms: identify yourself, use at most 4 decimals, and follow Expires/Last-Modified."""

    def setUp(self):
        metno._cache.clear()
        self.addCleanup(metno._cache.clear)
        self.requests = []
        self.responses = []
        self.clock = 1_000_000.0
        mock.patch.object(metno.time, "time", side_effect=lambda: self.clock).start()
        mock.patch.object(metno.urllib.request, "urlopen", side_effect=self.urlopen).start()
        self.addCleanup(mock.patch.stopall)

    def urlopen(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def http_date(self, seconds_from_now):
        moment = datetime.fromtimestamp(self.clock + seconds_from_now, timezone.utc)
        return moment.strftime("%a, %d %b %Y %H:%M:%S GMT")

    def ok(self, expires_in=1800):
        return FakeResponse({"properties": {"timeseries": []}},
                            headers(Expires=self.http_date(expires_in), Last_Modified="Fri, 13 Nov 2026 01:46:52 GMT"))

    def test_request_identifies_outpost_and_rounds_coordinates(self):
        self.responses = [self.ok()]
        metno.fetch_raw(59.912345678, 10.7522222, "Outpost/1 (me@example.com)")
        request = self.requests[0]
        self.assertIn("lat=59.9123&lon=10.7522", request.full_url)
        self.assertEqual(request.get_header("User-agent"), "Outpost/1 (me@example.com)")
        self.assertIsNone(request.get_header("If-modified-since"))

    def test_nothing_is_fetched_again_before_it_expires(self):
        self.responses = [self.ok(expires_in=1800)]
        metno.fetch_raw(1, 2, "ua")
        self.clock += 1700
        metno.fetch_raw(1, 2, "ua")
        self.assertEqual(len(self.requests), 1)

    def test_after_it_expires_it_is_revalidated(self):
        self.responses = [self.ok(expires_in=1800)]
        first = metno.fetch_raw(1, 2, "ua")
        self.clock += 1801
        self.responses = [urllib.error.HTTPError("u", 304, "Not Modified", headers(Expires=self.http_date(3600)), None)]
        again = metno.fetch_raw(1, 2, "ua")
        self.assertIs(again, first)
        self.assertEqual(self.requests[1].get_header("If-modified-since"), "Fri, 13 Nov 2026 01:46:52 GMT")
        self.clock += 1000  # the new Expires from the 304 is honored too
        metno.fetch_raw(1, 2, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_an_expiry_in_the_past_still_waits_a_minute(self):
        self.responses = [self.ok(expires_in=-60)]
        metno.fetch_raw(1, 2, "ua")
        self.clock += 30
        metno.fetch_raw(1, 2, "ua")
        self.assertEqual(len(self.requests), 1)
        self.clock += 31
        self.responses = [self.ok()]
        metno.fetch_raw(1, 2, "ua")
        self.assertEqual(len(self.requests), 2)

    def test_refusal_mentions_the_contact_setting(self):
        self.responses = [urllib.error.HTTPError("u", 403, "Forbidden", headers(), None)]
        with self.assertRaisesRegex(RuntimeError, "OUTPOST_CONTACT"):
            metno.fetch_raw(1, 2, "ua")

    def test_unreachable(self):
        self.responses = [urllib.error.URLError("no route")]
        with self.assertRaisesRegex(RuntimeError, "unreachable"):
            metno.fetch_raw(1, 2, "ua")


if __name__ == "__main__":
    unittest.main()
