"""Where alerts come from (OUTPOST_ALERTS_PROVIDER) and provider capabilities."""

import unittest
from unittest import mock

import helpers

import outpost_updater as u
from providers import nws, openmeteo
from test_updater import UpdaterTestCase, nws_data, openmeteo_data

US_ALERTS = [{"title": "Flood Watch", "description": "Sample", "severity": "moderate",
              "expires": "2026-11-13T00:00:00+00:00", "uri": None}]


class AlertsSourceTests(UpdaterTestCase):
    def run_update(self, provider="openmeteo", alerts_provider="auto"):
        with mock.patch.object(u, "PROVIDER", provider), mock.patch.object(u, "ALERTS_PROVIDER", alerts_provider), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()), \
                mock.patch.object(u.nws, "fetch", return_value=nws_data()):
            u.update_once()
        return self.output()

    def in_the_us(self):
        self.nws_alerts.side_effect = None
        self.nws_alerts.return_value = US_ALERTS

    def test_open_meteo_weather_gets_nws_alerts_in_the_us(self):
        self.in_the_us()
        data = self.run_update()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["sources"]["weather"]["id"], "openmeteo")
        self.assertEqual(data["sources"]["alerts"], {"id": "nws", "name": nws.SOURCE})
        self.assertEqual(data["alerts"], US_ALERTS)

    def test_open_meteo_weather_outside_the_us_has_no_alerts_source(self):
        data = self.run_update()
        self.assertEqual(data["status"], "ok")
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(data["alerts"], [])
        self.assertNotIn("OUTPOST_CONTACT", self.printed())  # NWS was not used, so no contact warning
        self.assertNotIn("OUTPOST_ALERTS_PROVIDER", self.printed())

    def test_a_provider_with_alerts_keeps_its_own(self):
        data = self.run_update(provider="nws")
        self.nws_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")
        self.assertEqual([a["title"] for a in data["alerts"]], ["Red Flag Warning", "Heat Advisory"])

    def test_mock_keeps_its_own_alerts(self):
        data = self.run_update(provider="mock")
        self.nws_alerts.assert_not_called()
        self.assertEqual(data["sources"]["alerts"]["id"], "mock")

    def test_none_turns_alerts_off(self):
        data = self.run_update(provider="nws", alerts_provider="none")
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(data["alerts"], [])

    def test_nws_can_be_chosen_for_any_weather_provider(self):
        self.in_the_us()
        data = self.run_update(provider="mock", alerts_provider="nws")
        self.assertEqual(data["sources"]["weather"]["id"], "mock")
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")
        self.assertEqual(data["alerts"], US_ALERTS)

    def test_nws_outside_the_us_warns_once(self):
        self.run_update(alerts_provider="nws")
        data = self.run_update(alerts_provider="nws")
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(self.printed().count("OUTPOST_ALERTS_PROVIDER=nws"), 1)

    def test_a_failed_alerts_lookup_keeps_fresh_weather_and_the_last_alerts(self):
        self.in_the_us()
        first = self.run_update()
        self.nws_alerts.side_effect = RuntimeError("NWS HTTP 503")
        data = self.run_update()
        self.assertEqual(data["status"], "degraded")
        self.assertTrue(data["last_error"].startswith("Alerts unavailable"))
        self.assertGreaterEqual(data["generated_at"], first["generated_at"])
        self.assertIsNotNone(data["current"]["temperature"])
        self.assertEqual(data["sources"]["alerts"]["id"], "nws")
        self.assertEqual(data["alerts"], US_ALERTS)

    def test_a_failed_alerts_lookup_does_not_keep_alerts_from_another_source(self):
        self.run_update(provider="mock")
        self.nws_alerts.side_effect = RuntimeError("NWS HTTP 503")
        data = self.run_update(provider="mock", alerts_provider="nws")
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["alerts"], [])

    def test_the_next_good_lookup_clears_the_error(self):
        self.in_the_us()
        self.nws_alerts.side_effect = RuntimeError("NWS HTTP 503")
        self.assertEqual(self.run_update()["status"], "degraded")
        self.nws_alerts.side_effect = None
        data = self.run_update()
        self.assertEqual(data["status"], "ok")
        self.assertIsNone(data["last_error"])

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)


class SettingTests(unittest.TestCase):
    def setUp(self):
        self.print = mock.patch("builtins.print").start()
        self.addCleanup(mock.patch.stopall)

    def test_default_is_auto(self):
        self.assertEqual(u.alerts_provider_setting(None), "auto")
        self.assertEqual(u.alerts_provider_setting(""), "auto")

    def test_values(self):
        for value in ("auto", "nws", "none", " NWS "):
            with self.subTest(value=value):
                self.assertEqual(u.alerts_provider_setting(value), value.strip().lower())
        self.print.assert_not_called()

    def test_unknown_value_warns_and_uses_auto(self):
        self.assertEqual(u.alerts_provider_setting("metalerts"), "auto")
        self.assertIn("OUTPOST_ALERTS_PROVIDER", self.print.call_args[0][0])


class CapabilityTests(unittest.TestCase):
    def test_every_provider_declares_what_it_supplies(self):
        known = {"current", "forecast", "alerts", "uv"}
        for name, capabilities in u.CAPABILITIES.items():
            with self.subTest(provider=name):
                self.assertLessEqual(set(capabilities), known)
                self.assertLessEqual({"current", "forecast"}, set(capabilities))

    def test_capabilities_match_the_data(self):
        # A provider without UV never sends one; a provider with UV does
        self.assertIsNone(nws_data()["current"]["uv_index"])
        self.assertIsNotNone(openmeteo_data()["current"]["uv_index"])
        self.assertEqual(openmeteo.CAPABILITIES, u.CAPABILITIES["openmeteo"])


if __name__ == "__main__":
    unittest.main()
