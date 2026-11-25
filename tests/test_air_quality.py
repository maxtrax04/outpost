"""Air quality and pollen (#88): weather.json "air_quality" (app/providers/airquality.py)."""

import unittest
from datetime import datetime, timezone
from unittest import mock

import helpers  # noqa: F401 (puts app/ on the path)

import outpost_updater as u
import regions
from providers import airquality
from test_data_format import SCHEMA, validate
from test_updater import UpdaterTestCase, openmeteo_data

# The "current" block of a real Air Quality API answer, outside Europe (no pollen)
CURRENT = {
    "time": "2026-11-25T14:00", "interval": 3600,
    "us_aqi": 40, "european_aqi": 48,
    "pm2_5": 12.04, "pm10": 12.4, "ozone": 22.0, "nitrogen_dioxide": 38.4,
    "sulphur_dioxide": 2.1, "carbon_monoxide": 244.0,
    "alder_pollen": None, "birch_pollen": None, "grass_pollen": None,
    "mugwort_pollen": None, "olive_pollen": None, "ragweed_pollen": None,
}
EUROPE = u.Location(50.0, 10.0, "Fictional Europe")
AMERICA = u.Location(40.0, -100.0, "Fictional Plains")


class BuildTests(unittest.TestCase):
    def test_readings(self):
        block = airquality.build(CURRENT, "us")
        self.assertEqual((block["index"], block["scale"], block["category"], block["level"]), (40, "us", "good", 0))
        self.assertEqual((block["us_aqi"], block["european_aqi"]), (40, 48))
        self.assertEqual(block["pm2_5"], 12.0)
        self.assertIsNone(block["pollen"])
        self.assertEqual(block["units"], {"pollutants": "µg/m³", "pollen": "grains/m³"})
        self.assertEqual(block["observed_at"], "2026-11-25T14:00:00+00:00")

    def test_the_european_index(self):
        block = airquality.build(CURRENT, "european")
        self.assertEqual((block["index"], block["category"], block["level"]), (48, "moderate", 2))

    def test_pollen(self):
        block = airquality.build({**CURRENT, "birch_pollen": 12.04, "grass_pollen": 0.0}, "european")
        self.assertEqual(block["pollen"]["birch"], 12.0)
        self.assertEqual(block["pollen"]["grass"], 0.0)
        self.assertIsNone(block["pollen"]["ragweed"])

    def test_nothing_known(self):
        self.assertIsNone(airquality.build({"time": "2026-11-25T14:00"}, "us"))
        self.assertIsNone(airquality.build(None, "us"))

    def test_broken_values(self):
        block = airquality.build({**CURRENT, "us_aqi": "40", "pm10": -3, "ozone": float("nan")}, "us")
        self.assertEqual((block["index"], block["category"], block["level"]), (None, None, None))
        self.assertEqual(block["pm10"], 0.0)
        self.assertIsNone(block["ozone"])
        self.assertIsNone(airquality.build({**CURRENT, "time": "soon"}, "us")["observed_at"])

    def test_bands(self):
        cases = {
            "us": [(0, "good", 0), (50, "good", 0), (51, "moderate", 1), (101, "unhealthy-sensitive", 2),
                   (151, "unhealthy", 3), (201, "very-unhealthy", 4), (301, "hazardous", 5), (900, "hazardous", 5)],
            "european": [(20, "good", 0), (21, "fair", 1), (41, "moderate", 2), (61, "poor", 3),
                         (81, "very-poor", 4), (101, "extremely-poor", 5)],
        }
        for scale, values in cases.items():
            for value, name, level in values:
                with self.subTest(scale=scale, value=value):
                    self.assertEqual(airquality.category(scale, value), {"category": name, "level": level})
        self.assertEqual(airquality.category("us", None), {"category": None, "level": None})

    def test_every_category_is_in_the_schema(self):
        names = {name for bands in airquality.SCALES.values() for _, name in bands}
        self.assertEqual(names | {None}, set(SCHEMA["properties"]["air_quality"]["anyOf"][1]["properties"]["category"]["enum"]))


class FetchTests(unittest.TestCase):
    def setUp(self):
        mock.patch.dict(airquality._cache, clear=True).start()
        self.addCleanup(mock.patch.stopall)

    def test_asked_once_an_hour(self):
        self.assertEqual(airquality.cache_until(datetime(2026, 11, 25, 14, 2, tzinfo=timezone.utc).timestamp()),
                         datetime(2026, 11, 25, 15, 5, tzinfo=timezone.utc).timestamp())
        self.assertEqual(airquality.cache_until(datetime(2026, 11, 25, 14, 59, tzinfo=timezone.utc).timestamp()),
                         datetime(2026, 11, 25, 15, 5, tzinfo=timezone.utc).timestamp())

    def test_the_answer_is_reused_until_then(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        with mock.patch.object(airquality.urllib.request, "urlopen", return_value=response) as urlopen, \
                mock.patch.object(airquality.json, "load", return_value={"current": CURRENT}):
            first = airquality.fetch(10.0, 20.0, "us", "Outpost/test")
            second = airquality.fetch(10.0, 20.0, "us", "Outpost/test")
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(first, second)
        url = urlopen.call_args[0][0].full_url
        self.assertTrue(url.startswith(airquality.API_URL))
        for name in ("us_aqi", "pm2_5", "birch_pollen"):
            self.assertIn(name, url)

    def test_an_error_answer(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        with mock.patch.object(airquality.urllib.request, "urlopen", return_value=response), \
                mock.patch.object(airquality.json, "load", return_value={"error": True, "reason": "Bad latitude"}):
            with self.assertRaisesRegex(RuntimeError, "Bad latitude"):
                airquality.fetch(10.0, 20.0, "us", "Outpost/test")


class SettingTests(unittest.TestCase):
    def test_index_setting(self):
        for value, expected in ((None, "auto"), ("", "auto"), ("US", "us"), (" european ", "european")):
            with self.subTest(value=value):
                self.assertEqual(u.air_quality_index_setting(value), expected)
        with mock.patch("builtins.print") as printed:
            self.assertEqual(u.air_quality_index_setting("aqhi"), "auto")
        self.assertIn("OUTPOST_AIR_QUALITY_INDEX", printed.call_args[0][0])

    def test_auto_picks_by_region(self):
        with mock.patch.object(u, "AIR_QUALITY_INDEX", "auto"):
            self.assertEqual(u.air_quality_scale(EUROPE), "european")
            self.assertEqual(u.air_quality_scale(AMERICA), "us")
        with mock.patch.object(u, "AIR_QUALITY_INDEX", "us"):
            self.assertEqual(u.air_quality_scale(EUROPE), "us")

    def test_the_european_area(self):
        self.assertTrue(regions.in_cams_europe(59.9, 10.7))
        self.assertTrue(regions.in_cams_europe(37.0, -8.0))
        self.assertFalse(regions.in_cams_europe(40.0, -100.0))
        self.assertFalse(regions.in_cams_europe(-33.9, 18.4))

    def test_off_by_default_in_tests_on_otherwise(self):
        # helpers.py turns it off so no test reaches the service; the setting's own default is on
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertTrue(u.env_flag("OUTPOST_AIR_QUALITY", True))
        self.assertFalse(u.AIR_QUALITY)

    def test_documented(self):
        for path in ("README.md", ".env.example"):
            text = (helpers.ROOT / path).read_text(encoding="utf-8")
            for name in ("OUTPOST_AIR_QUALITY", "OUTPOST_AIR_QUALITY_INDEX"):
                with self.subTest(path=path, name=name):
                    self.assertIn(name, text)


class UpdateTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.object(u, "AIR_QUALITY", True).start()
        mock.patch.object(u, "AIR_QUALITY_INDEX", "auto").start()
        mock.patch.object(u, "PROVIDER", "openmeteo").start()
        mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()).start()
        self.fetch = mock.patch.object(u.airquality, "fetch_raw", return_value={"current": CURRENT}).start()

    def test_in_the_file_and_credited(self):
        u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sources"]["air_quality"],
                         {"id": "openmeteo-air-quality", "name": airquality.SOURCE})
        self.assertEqual(data["air_quality"]["index"], 40)
        # Fictional home at 10, 20 is outside Europe
        self.assertEqual(data["air_quality"]["scale"], "us")
        self.assertEqual(validate(data, SCHEMA), [])

    def test_other_places_get_their_own(self):
        payload = u.update_once(EUROPE, u.LocationState())
        self.assertEqual(payload["air_quality"]["scale"], "european")
        self.assertEqual(self.fetch.call_args[0][:2], (50.0, 10.0))

    def test_off(self):
        with mock.patch.object(u, "AIR_QUALITY", False):
            u.update_once()
        data = self.output()
        self.fetch.assert_not_called()
        self.assertIsNone(data["air_quality"])
        self.assertIsNone(data["sources"]["air_quality"])

    def test_a_failure_keeps_the_last_readings_and_the_weather(self):
        u.update_once()
        self.fetch.side_effect = RuntimeError("Open-Meteo air quality unreachable: timed out")
        u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["last_error"], "Air quality unavailable: Open-Meteo air quality unreachable: timed out")
        self.assertEqual(data["air_quality"]["index"], 40)
        self.assertIsNotNone(data["current"]["temperature"])

    def test_a_failure_with_nothing_before(self):
        self.fetch.side_effect = RuntimeError("boom")
        u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "degraded")
        self.assertIsNone(data["air_quality"])
        self.assertEqual(data["sources"]["air_quality"]["id"], "openmeteo-air-quality")

    def test_both_errors_are_reported(self):
        payload = u.build_live_payload("openmeteo", openmeteo_data(),
                                       {"source": None, "alerts": [], "error": "Alerts unavailable: x"},
                                       air={"source": None, "air_quality": None, "error": "Air quality unavailable: y"})
        self.assertEqual(payload["last_error"], "Alerts unavailable: x; Air quality unavailable: y")

    def test_the_mock_has_samples_with_pollen(self):
        with mock.patch.object(u, "PROVIDER", "mock"):
            u.update_once()
        data = self.output()
        self.fetch.assert_not_called()
        self.assertEqual(data["sources"]["air_quality"]["id"], "mock")
        self.assertIsNotNone(data["air_quality"]["pollen"])
        self.assertEqual(validate(data, SCHEMA), [])
        self.assertEqual(validate(u.build_mock_payload(), SCHEMA), [])


if __name__ == "__main__":
    unittest.main()
