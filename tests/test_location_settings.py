"""OUTPOST_LOCATION_SEARCH, OUTPOST_LOCATION_LIMIT, OUTPOST_LOCATION_PIRATEWEATHER, and Pirate Weather's spare quota."""

import io
import json
import unittest
from unittest import mock

import helpers

import outpost_updater as u
from providers import pirateweather
from test_pirateweather import pirate_data
from test_updater import UpdaterTestCase, openmeteo_data

NOW = 1_800_000_000.0
DAY = 24 * 3600
ELSEWHERE = u.Location(-30.0, 135.0, "Dry Hollow")


class SettingTests(unittest.TestCase):
    def test_defaults(self):
        self.assertIs(u.LOCATION_SEARCH, True)
        self.assertEqual(u.LOCATION_LIMIT, 30)
        self.assertIs(u.LOCATION_PIRATEWEATHER, True)

    def test_the_limit(self):
        with mock.patch("builtins.print") as printed:
            for value, expected in ((None, 30), ("", 30), (" 12 ", 12), ("0", 0), ("-1", 30), ("lots", 30)):
                with self.subTest(value=value):
                    self.assertEqual(u.location_limit_setting(value), expected)
        self.assertEqual(printed.call_count, 2)

    def test_the_flags(self):
        for value, expected in (("false", False), ("0", False), ("true", True), ("", True)):
            with self.subTest(value=value), mock.patch.dict("os.environ", {"OUTPOST_LOCATION_SEARCH": value}):
                self.assertIs(u.env_flag("OUTPOST_LOCATION_SEARCH", True), expected)

    def test_every_setting_is_documented(self):
        example = (helpers.ROOT / ".env.example").read_text(encoding="utf-8")
        readme = (helpers.ROOT / "README.md").read_text(encoding="utf-8")
        for name in ("OUTPOST_LOCATION_SEARCH", "OUTPOST_LOCATION_LIMIT", "OUTPOST_LOCATION_PIRATEWEATHER"):
            self.assertIn(f"{name}=", example)
            self.assertIn(f"| `{name}` |", readme)


class QuotaTests(unittest.TestCase):
    def setUp(self):
        pirateweather._quota.clear()
        self.addCleanup(pirateweather._quota.clear)

    def test_nothing_is_spare_before_pirate_weather_has_said(self):
        self.assertEqual(pirateweather.spare_calls(600, NOW), 0)

    def test_the_design_note_example(self):
        # 6,000 calls left, 10 days to the reset, home at most every 10 minutes: 1,440 calls, 1,584 with 10%
        pirateweather._note_quota({"Ratelimit-Remaining": "6000", "Ratelimit-Reset": str(10 * DAY)}, NOW)
        self.assertEqual(pirateweather.spare_calls(600, NOW), 6000 - 1584)

    def test_too_little_left_means_none_spare(self):
        pirateweather._note_quota({"Ratelimit-Remaining": "1500", "Ratelimit-Reset": str(10 * DAY)}, NOW)
        self.assertEqual(pirateweather.spare_calls(600, NOW), 0)

    def test_what_was_said_before_the_reset_is_not_used(self):
        pirateweather._note_quota({"Ratelimit-Remaining": "9000", "Ratelimit-Reset": "60"}, NOW)
        self.assertEqual(pirateweather.spare_calls(600, NOW + 61), 0)

    def test_missing_or_bad_headers_are_ignored(self):
        for headers in ({}, {"Ratelimit-Remaining": "9000"}, {"Ratelimit-Remaining": "x", "Ratelimit-Reset": "60"},
                        {"Ratelimit-Remaining": "9000", "Ratelimit-Reset": "-5"}):
            pirateweather._note_quota(headers, NOW)
            self.assertEqual(pirateweather._quota, {})

    def test_a_successful_answer_records_the_quota(self):
        class Response(io.BytesIO):
            headers = {"Ratelimit-Remaining": "4321", "Ratelimit-Reset": "3600"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        pirateweather._cache.clear()
        self.addCleanup(pirateweather._cache.clear)
        answer = Response(json.dumps({"currently": {}}).encode())
        with mock.patch("urllib.request.urlopen", return_value=answer), \
                mock.patch.object(pirateweather, "_blocked_until", 0.0), \
                mock.patch.object(pirateweather.time, "time", return_value=NOW):
            pirateweather.fetch_raw(1.0, 2.0, "key", "test")
        self.assertEqual(pirateweather._quota, {"remaining": 4321, "reset_at": NOW + 3600})

    def test_quota_reached_leaves_nothing_spare(self):
        error = pirateweather.urllib.error.HTTPError("url", 429, "Too Many", {"Ratelimit-Reset": "7200"}, None)
        pirateweather._cache.clear()
        with mock.patch("urllib.request.urlopen", side_effect=error), \
                mock.patch.object(pirateweather, "_blocked_until", 0.0), \
                mock.patch.object(pirateweather.time, "time", return_value=NOW), self.assertRaises(RuntimeError):
            pirateweather.fetch_raw(1.0, 2.0, "key", "test")
        self.assertEqual(pirateweather._quota["remaining"], 0)
        self.assertEqual(pirateweather.spare_calls(600, NOW), 0)


class PirateKeyTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        pirateweather._quota.clear()
        self.addCleanup(pirateweather._quota.clear)
        mock.patch.object(u, "PIRATEWEATHER_API_KEY", "secret").start()
        self.spare = mock.patch.object(pirateweather, "spare_calls", return_value=100).start()

    def test_home_always_gets_the_key(self):
        self.spare.return_value = 0
        self.assertEqual(u.pirate_key(), "secret")

    def test_another_place_gets_it_only_with_spare_calls(self):
        self.assertEqual(u.pirate_key(ELSEWHERE), "secret")
        self.spare.return_value = 0
        self.assertEqual(u.pirate_key(ELSEWHERE), "")

    def test_home_needs_one_call_per_update_or_per_ten_minutes(self):
        with mock.patch.object(u, "UPDATE_INTERVAL", 60):
            u.pirate_key(ELSEWHERE)
        self.assertEqual(self.spare.call_args.args[0], pirateweather.MIN_CACHE_SECONDS)
        with mock.patch.object(u, "UPDATE_INTERVAL", 1800):
            u.pirate_key(ELSEWHERE)
        self.assertEqual(self.spare.call_args.args[0], 1800)

    def test_the_setting_keeps_the_key_for_home(self):
        with mock.patch.object(u, "LOCATION_PIRATEWEATHER", False):
            self.assertEqual(u.pirate_key(ELSEWHERE), "")
            self.assertEqual(u.pirate_key(), "secret")

    def test_without_spare_calls_another_place_uses_open_meteo(self):
        self.spare.return_value = 0
        with mock.patch.object(u, "PROVIDER", "pirateweather"), \
                mock.patch.object(u.pirateweather, "fetch", return_value=pirate_data()) as pirate, \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            payload = u.update_once(ELSEWHERE, u.LocationState())
            self.assertEqual(payload["sources"]["weather"]["id"], "openmeteo")
            pirate.assert_not_called()
            # Home still uses Pirate Weather
            self.assertEqual(u.update_once()["sources"]["weather"]["id"], "pirateweather")

    def test_auto_with_spare_calls_uses_pirate_weather_for_another_place(self):
        with mock.patch.object(u, "PROVIDER", "auto"), \
                mock.patch.object(u.nws, "fetch", side_effect=u.nws.NoCoverageError("US only")), \
                mock.patch.object(u.pirateweather, "fetch", return_value=pirate_data()), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            self.assertEqual(u.update_once(ELSEWHERE, u.LocationState())["sources"]["weather"]["id"], "pirateweather")
            self.spare.return_value = 0
            self.assertEqual(u.update_once(ELSEWHERE, u.LocationState())["sources"]["weather"]["id"], "openmeteo")

    def test_without_spare_calls_another_place_has_no_pirate_weather_alerts(self):
        self.spare.return_value = 0
        with mock.patch.object(u, "ALERTS_PROVIDER", "pirateweather"):
            self.assertIsNone(u.resolve_alerts("openmeteo", openmeteo_data(), ELSEWHERE, u.LocationState())["source"])
        self.pirate_alerts.assert_not_called()
        self.assertNotIn("needs", " ".join(str(c.args) for c in self.print.call_args_list))


if __name__ == "__main__":
    unittest.main()
