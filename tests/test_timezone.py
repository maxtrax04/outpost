"""weather.json "timezone": the location's time zone, for showing times as they are there."""

import os
import unittest
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
from providers import nws
from test_pirateweather import pirate_data
from test_updater import UpdaterTestCase, metno_data, nws_data, openmeteo_data


class TimezoneTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.dict(os.environ, {"TZ": "Europe/Oslo"}).start()

    def test_from_the_weather_service(self):
        nws_with_zone = {**nws_data(), "timezone": "America/Chicago"}
        cases = {
            "openmeteo": (openmeteo_data(), "UTC"),
            "nws": (nws_with_zone, "America/Chicago"),
            "pirateweather": (pirate_data(), "America/Chicago"),
        }
        for provider, (data, expected) in cases.items():
            with self.subTest(provider=provider):
                self.assertEqual(u.build_live_payload(provider, data)["timezone"], expected)

    def test_otherwise_the_containers_tz_setting(self):
        self.assertEqual(u.build_live_payload("metno", metno_data())["timezone"], "Europe/Oslo")
        self.assertEqual(u.build_mock_payload()["timezone"], "Europe/Oslo")
        self.assertEqual(u.build_error_payload("boom")["timezone"], "Europe/Oslo")

    def test_an_unknown_name_is_not_passed_on(self):
        data = {**openmeteo_data(), "timezone": "Not/AZone"}
        self.assertEqual(u.build_live_payload("openmeteo", data)["timezone"], "Europe/Oslo")
        for name in ("../../etc/passwd", "", None, 5):
            with self.subTest(name=name):
                self.assertIsNone(u.valid_timezone(name))

    def test_null_when_unknown(self):
        with mock.patch.dict(os.environ, {"TZ": ""}):
            self.assertIsNone(u.build_live_payload("metno", metno_data())["timezone"])

    def test_nws_reports_the_zone_from_its_location_lookup(self):
        nws._point_cache.clear()
        self.addCleanup(nws._point_cache.clear)

        def fake_get(url, user_agent):
            if "/points/" in url:
                return load_fixture("nws_points.json")
            if url.endswith("/forecast"):
                return load_fixture("nws_forecast.json")
            if url.endswith("/stations"):
                return {"features": []}
            if "/alerts/active" in url:
                return {"features": []}
            raise AssertionError(url)

        with mock.patch.object(nws, "_get", side_effect=fake_get):
            self.assertEqual(nws.fetch(10.0, 20.0, "ua")["timezone"], "America/Chicago")


if __name__ == "__main__":
    unittest.main()
