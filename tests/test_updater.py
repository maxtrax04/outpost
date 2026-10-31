import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT, load_fixture

import outpost_updater as u
from providers import nws, openmeteo

DIM_VARS = ["OUTPOST_AUTO_DIM", "OUTPOST_DIM_LEVEL", "OUTPOST_DIM_MODE", "OUTPOST_DIM_START", "OUTPOST_DIM_END"]


def nws_data():
    obs = load_fixture("nws_observation.json")
    from datetime import datetime, timezone
    obs["properties"]["timestamp"] = datetime.now(timezone.utc).isoformat()
    return nws.normalize(load_fixture("nws_forecast.json")["properties"]["periods"],
                         obs["properties"], load_fixture("nws_alerts.json")["features"])


def openmeteo_data():
    return openmeteo.normalize(load_fixture("openmeteo.json"))


class UpdaterTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data_dir = Path(folder.name)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(u, "DATA_PATH", self.data_dir / "weather.json").start()
        mock.patch.object(u, "PROVIDER", "mock").start()
        mock.patch.object(u, "LOCATION_NAME", "Test Site").start()
        mock.patch.object(u, "_warned_user_agent", False).start()
        self.print = mock.patch("builtins.print").start()

    def output(self):
        return json.loads((self.data_dir / "weather.json").read_text())

    def config(self):
        return json.loads((self.data_dir / "config.json").read_text())


class VersionTests(UpdaterTestCase):
    def test_version_comes_from_the_version_file(self):
        self.assertEqual(u.APP_VERSION, (ROOT / "VERSION").read_text().strip())

    def test_default_user_agent_includes_the_version(self):
        self.assertEqual(u.USER_AGENT, f"Outpost/{u.APP_VERSION}")


class UserAgentTests(UpdaterTestCase):
    def test_without_contact(self):
        self.assertEqual(u.build_user_agent("1.2.3"), "Outpost/1.2.3")

    def test_with_contact(self):
        self.assertEqual(u.build_user_agent("1.2.3", "me@example.com"), "Outpost/1.2.3 (me@example.com)")

    def test_override_replaces_everything(self):
        self.assertEqual(u.build_user_agent("1.2.3", "me@example.com", "Custom/1"), "Custom/1")

    def test_valid_header_text_is_kept(self):
        for value in ("me@example.com", "https://example.com/outpost", "  padded@example.com  "):
            with self.subTest(value=value):
                self.assertEqual(u.clean_header_text("X", value), value.strip())

    def test_unsafe_header_text_is_rejected(self):
        for value in ("line\nbreak", "x\r\nX-Injected: 1", "caf\u00e9@example.com", "a" * 121, "tab\tcharacter"):
            with self.subTest(value=value):
                self.assertEqual(u.clean_header_text("X", value), "")

    def test_empty_text_is_empty(self):
        self.assertEqual(u.clean_header_text("X", "   "), "")

    def test_settings_are_read_from_the_environment(self):
        with mock.patch.dict(os.environ, {"OUTPOST_CONTACT": "me@example.com"}):
            contact, agent = u.load_contact_settings()
        self.assertEqual(contact, "me@example.com")
        self.assertEqual(agent, f"Outpost/{u.APP_VERSION} (me@example.com)")

    def test_override_is_read_from_the_environment(self):
        with mock.patch.dict(os.environ, {"OUTPOST_CONTACT": "me@example.com", "OUTPOST_USER_AGENT": "Custom/1"}):
            self.assertEqual(u.load_contact_settings()[1], "Custom/1")

    def test_an_invalid_contact_is_ignored(self):
        with mock.patch.dict(os.environ, {"OUTPOST_CONTACT": "bad\nvalue"}):
            contact, agent = u.load_contact_settings()
        self.assertEqual(contact, "")
        self.assertEqual(agent, f"Outpost/{u.APP_VERSION}")

    def printed(self):
        return " ".join(str(call) for call in self.print.call_args_list)

    def test_warns_when_no_contact_is_set(self):
        with mock.patch.object(u, "CONTACT", ""), mock.patch.object(u, "USER_AGENT", "Outpost/1"):
            u.warn_about_user_agent()
        self.assertIn("OUTPOST_CONTACT", self.printed())

    def test_no_warning_when_a_contact_is_set(self):
        with mock.patch.object(u, "CONTACT", "me@example.com"), mock.patch.object(u, "USER_AGENT", "Outpost/1 (me@example.com)"):
            u.warn_about_user_agent()
        self.print.assert_not_called()

    def test_an_override_containing_contact_info_counts(self):
        with mock.patch.object(u, "CONTACT", ""), mock.patch.object(u, "USER_AGENT", "Custom (https://example.com)"):
            u.warn_about_user_agent()
        self.print.assert_not_called()

    def test_warns_only_once(self):
        with mock.patch.object(u, "CONTACT", ""), mock.patch.object(u, "USER_AGENT", "Outpost/1"):
            u.warn_about_user_agent()
            u.warn_about_user_agent()
        self.assertEqual(self.print.call_count, 1)

    def test_nws_updates_warn_but_open_meteo_updates_do_not(self):
        with mock.patch.object(u, "CONTACT", ""), mock.patch.object(u, "USER_AGENT", "Outpost/1"):
            with mock.patch.object(u, "PROVIDER", "openmeteo"), \
                    mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
                u.update_once()
            self.assertNotIn("OUTPOST_CONTACT", self.printed())
            with mock.patch.object(u, "PROVIDER", "nws"), mock.patch.object(u.nws, "fetch", return_value=nws_data()):
                u.update_once()
            self.assertIn("OUTPOST_CONTACT", self.printed())

    def test_the_user_agent_is_sent_to_the_provider(self):
        with mock.patch.object(u, "PROVIDER", "nws"), mock.patch.object(u, "USER_AGENT", "Outpost/9 (me@example.com)"), \
                mock.patch.object(u.nws, "fetch", return_value=nws_data()) as fetch:
            u.update_once()
        fetch.assert_called_once_with(u.LATITUDE, u.LONGITUDE, "Outpost/9 (me@example.com)")


class MockProviderTests(UpdaterTestCase):
    def test_payload_contract(self):
        u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], u.APP_VERSION)
        self.assertEqual(data["update_interval_seconds"], u.UPDATE_INTERVAL)
        for key in ("status", "provider", "location", "generated_at", "current", "forecast", "alerts", "alerts_supported", "coordinates"):
            self.assertIn(key, data)
        for key in ("temperature_f", "feels_like_f", "condition", "icon", "humidity_percent",
                    "wind_mph", "pressure_inhg", "uv_index", "visibility_miles"):
            self.assertIn(key, data["current"])
        for key in ("day", "high_f", "low_f", "condition", "icon", "precipitation_percent", "uv_index"):
            self.assertIn(key, data["forecast"][0])

    def test_mock_data_supports_alerts(self):
        u.update_once()
        self.assertTrue(self.output()["alerts_supported"])

    def test_feels_like_is_close_to_the_temperature(self):
        for _ in range(50):
            current = u.build_mock_payload()["current"]
            self.assertLessEqual(abs(current["feels_like_f"] - current["temperature_f"]), 6)

    def test_unknown_provider_writes_an_error_payload(self):
        with mock.patch.object(u, "PROVIDER", "nonsense"):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "error")
        self.assertIn("not implemented", data["last_error"])


class LiveProviderTests(UpdaterTestCase):
    def test_openmeteo(self):
        with mock.patch.object(u, "PROVIDER", "openmeteo"), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        data = self.output()
        self.assertEqual((data["status"], data["provider"], data["provider_setting"]), ("ok", "openmeteo", "openmeteo"))
        self.assertEqual(data["source"], "Open-Meteo.com")
        self.assertEqual(data["filled_fields"], [])
        self.assertFalse(data["alerts_supported"])

    def test_nws_does_not_gap_fill(self):
        with mock.patch.object(u, "PROVIDER", "nws"), \
                mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.openmeteo, "fetch") as backup:
            u.update_once()
        backup.assert_not_called()
        self.assertIsNone(self.output()["current"]["uv_index"])

    def test_failure_keeps_the_last_good_data(self):
        with mock.patch.object(u, "PROVIDER", "openmeteo"):
            with mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
                u.update_once()
            first = self.output()
            with mock.patch.object(u.openmeteo, "fetch", side_effect=RuntimeError("Open-Meteo unreachable")):
                u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["last_error"], "Open-Meteo unreachable")
        self.assertEqual(data["generated_at"], first["generated_at"])
        self.assertEqual(data["current"]["temperature_f"], first["current"]["temperature_f"])

    def test_failure_with_no_previous_data_writes_an_error(self):
        with mock.patch.object(u, "PROVIDER", "openmeteo"), \
                mock.patch.object(u.openmeteo, "fetch", side_effect=RuntimeError("boom")):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["current"]["condition"], "DATA LINK LOST")
        self.assertFalse(data["alerts_supported"])

    def test_old_data_for_another_location_is_not_reused(self):
        with mock.patch.object(u, "PROVIDER", "openmeteo"):
            with mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
                u.update_once()
            with mock.patch.object(u, "LOCATION_NAME", "Somewhere Else"), \
                    mock.patch.object(u.openmeteo, "fetch", side_effect=RuntimeError("boom")):
                u.update_once()
        self.assertEqual(self.output()["status"], "error")


class AutoProviderTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.object(u, "PROVIDER", "auto").start()

    def test_outside_the_us_uses_open_meteo(self):
        with mock.patch.object(u.nws, "fetch", side_effect=nws.NoCoverageError("US only")), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        data = self.output()
        self.assertEqual((data["status"], data["provider"], data["provider_setting"]), ("ok", "openmeteo", "auto"))
        self.assertFalse(data["alerts_supported"])

    def test_us_uses_nws_and_fills_gaps_from_open_meteo(self):
        with mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        data = self.output()
        self.assertEqual(data["provider"], "nws")
        self.assertIn("current.uv_index", data["filled_fields"])
        self.assertIsNotNone(data["current"]["uv_index"])
        self.assertIn("National Weather Service", data["source"])
        self.assertIn("Open-Meteo.com", data["source"])
        self.assertEqual(data["current"]["condition"], "Fair")  # NWS wording is kept
        self.assertEqual(len(data["alerts"]), 2)
        self.assertTrue(data["alerts_supported"])  # still true after gap filling

    def test_open_meteo_failure_does_not_fail_the_update(self):
        with mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.openmeteo, "fetch", side_effect=RuntimeError("down")):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["filled_fields"], [])
        self.assertIsNone(data["current"]["uv_index"])

    def test_nws_failure_is_not_hidden_by_switching_providers(self):
        with mock.patch.object(u.nws, "fetch", side_effect=RuntimeError("NWS HTTP 503")), \
                mock.patch.object(u.openmeteo, "fetch") as backup:
            u.update_once()
        backup.assert_not_called()
        self.assertEqual(self.output()["status"], "error")

    def test_degraded_data_is_kept_in_auto_mode(self):
        with mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        with mock.patch.object(u.nws, "fetch", side_effect=RuntimeError("NWS HTTP 503")):
            u.update_once()
        data = self.output()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["provider"], "nws")


class ConfigTests(UpdaterTestCase):
    def write_with_env(self, env=None, theme="retro-crt", themes_dir=None):
        with mock.patch.dict(os.environ):
            for name in DIM_VARS:
                os.environ.pop(name, None)
            os.environ.update(env or {})
            with mock.patch.object(u, "THEME", theme), \
                    mock.patch.object(u, "THEMES_DIR", themes_dir or Path("/does/not/exist")):
                u.write_config()
        return self.config()

    def test_defaults(self):
        config = self.write_with_env()
        self.assertEqual(config["theme"], "retro-crt")
        self.assertEqual(config["dim"], {"enabled": True, "level": 0.35, "mode": "sun", "start": "22:00", "end": "06:00"})
        self.assertEqual((config["latitude"], config["longitude"]), (u.LATITUDE, u.LONGITUDE))
        self.assertEqual(config["version"], u.APP_VERSION)

    def test_custom_dim_settings(self):
        config = self.write_with_env({"OUTPOST_AUTO_DIM": "off", "OUTPOST_DIM_LEVEL": "0.2", "OUTPOST_DIM_MODE": "schedule",
                                      "OUTPOST_DIM_START": "21:30", "OUTPOST_DIM_END": "7:00"})
        self.assertEqual(config["dim"], {"enabled": False, "level": 0.2, "mode": "schedule", "start": "21:30", "end": "7:00"})

    def test_bad_dim_values_use_defaults(self):
        config = self.write_with_env({"OUTPOST_DIM_LEVEL": "dark", "OUTPOST_DIM_MODE": "moon", "OUTPOST_DIM_START": "99:99"})
        self.assertEqual(config["dim"]["level"], 0.35)
        self.assertEqual(config["dim"]["mode"], "sun")
        self.assertEqual(config["dim"]["start"], "22:00")

    def test_level_is_clamped(self):
        self.assertEqual(self.write_with_env({"OUTPOST_DIM_LEVEL": "0"})["dim"]["level"], 0.05)
        self.assertEqual(self.write_with_env({"OUTPOST_DIM_LEVEL": "5"})["dim"]["level"], 1.0)

    def test_ui_defaults(self):
        config = self.write_with_env({"OUTPOST_SUBTITLE": "", "OUTPOST_ALERTS_ALWAYS_SHOW": ""})
        self.assertEqual(config["ui"], {"subtitle": "", "alerts_always_show": False})

    def test_ui_settings(self):
        config = self.write_with_env({"OUTPOST_SUBTITLE": "  {date}  ", "OUTPOST_ALERTS_ALWAYS_SHOW": "True"})
        self.assertEqual(config["ui"], {"subtitle": "{date}", "alerts_always_show": True})

    def test_alerts_flag_accepts_common_spellings(self):
        for value, expected in (("1", True), ("yes", True), ("ON", True), ("false", False), ("0", False), ("nonsense", False)):
            with self.subTest(value=value):
                config = self.write_with_env({"OUTPOST_ALERTS_ALWAYS_SHOW": value})
                self.assertEqual(config["ui"]["alerts_always_show"], expected)

    def test_long_subtitles_are_shortened(self):
        config = self.write_with_env({"OUTPOST_SUBTITLE": "x" * 200})
        self.assertEqual(len(config["ui"]["subtitle"]), 80)

    def test_invalid_theme_names_are_rejected(self):
        for bad in ("../etc/passwd", "My Theme", "UPPER", ""):
            with self.subTest(theme=bad):
                self.assertEqual(self.write_with_env(theme=bad)["theme"], "retro-crt")

    def test_unknown_theme_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "retro-crt.css").write_text("")
            self.assertEqual(self.write_with_env(theme="nope", themes_dir=Path(folder))["theme"], "retro-crt")

    def test_existing_theme_is_used(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "mine.css").write_text("")
            self.assertEqual(self.write_with_env(theme="mine", themes_dir=Path(folder))["theme"], "mine")


if __name__ == "__main__":
    unittest.main()
