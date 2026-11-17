"""Updating a place other than home: its own payload and fallback state, and weather.json untouched."""

import unittest
from unittest import mock

import helpers

import outpost_updater as u
from test_updater import UpdaterTestCase, metno_data, openmeteo_data

# Made-up places: one inside MET Norway's area, one elsewhere (outside NWS coverage in these tests)
FJORDVIK = u.Location(60.0, 10.0, "Fjordvik")
DRY_HOLLOW = u.Location(-30.0, 135.0, "Dry Hollow")

ALERT = {"title": "Wind Warning", "description": "Strong wind", "severity": "moderate", "expires": None, "uri": None}


class LocationTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.object(u, "PROVIDER", "auto").start()
        mock.patch.object(u, "PIRATEWEATHER_API_KEY", "").start()
        self.metno_fetch = mock.patch.object(u.metno, "fetch", side_effect=lambda *a: metno_data()).start()
        self.openmeteo_fetch = mock.patch.object(u.openmeteo, "fetch", side_effect=lambda *a: openmeteo_data()).start()
        mock.patch.object(u.nws, "fetch", side_effect=u.nws.NoCoverageError("US only")).start()

    def test_home_is_the_settings(self):
        with mock.patch.object(u, "LATITUDE", 1.5), mock.patch.object(u, "LONGITUDE", 2.5):
            self.assertEqual(u.home_location(), u.Location(1.5, 2.5, "Test Site", home=True))

    def test_another_place_is_not_written_to_weather_json(self):
        state = u.LocationState()
        payload = u.update_once(DRY_HOLLOW, state)
        self.assertFalse((self.data_dir / "weather.json").exists())
        self.assertEqual(payload["location"], "Dry Hollow")
        self.assertEqual(payload["coordinates"], {"latitude": -30.0, "longitude": 135.0})
        self.assertEqual(state.read(), payload)

    def test_home_is_still_written_to_weather_json(self):
        payload = u.update_once()
        self.assertEqual(self.output(), payload)
        self.assertEqual(payload["location"], "Test Site")

    def test_each_place_gets_its_own_provider(self):
        self.assertEqual(u.update_once(FJORDVIK, u.LocationState())["sources"]["weather"]["id"], "metno")
        self.assertEqual(u.update_once(DRY_HOLLOW, u.LocationState())["sources"]["weather"]["id"], "openmeteo")
        self.assertEqual(self.metno_fetch.call_args.args[:2], (60.0, 10.0))
        self.assertEqual(self.openmeteo_fetch.call_args.args[:2], (-30.0, 135.0))

    def test_a_failure_keeps_that_places_last_good_data(self):
        state = u.LocationState()
        good = u.update_once(DRY_HOLLOW, state)
        self.openmeteo_fetch.side_effect = RuntimeError("Open-Meteo unreachable")
        payload = u.update_once(DRY_HOLLOW, state)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["current"], good["current"])
        self.assertEqual(payload["last_error"], "Open-Meteo unreachable")
        self.assertEqual(state.read()["status"], "degraded")

    def test_a_failure_without_good_data_names_the_place(self):
        self.openmeteo_fetch.side_effect = RuntimeError("Open-Meteo unreachable")
        payload = u.update_once(DRY_HOLLOW, u.LocationState())
        self.assertEqual((payload["status"], payload["location"]), ("error", "Dry Hollow"))
        self.assertEqual(payload["coordinates"], {"latitude": -30.0, "longitude": 135.0})

    def test_home_data_is_never_used_for_another_place(self):
        u.update_once()  # good data at home
        self.openmeteo_fetch.side_effect = RuntimeError("Open-Meteo unreachable")
        self.assertEqual(u.update_once(DRY_HOLLOW, u.LocationState())["status"], "error")

    def test_a_place_with_no_data_switches_to_open_meteo_at_once(self):
        # Home has fresh MET Norway data, but this place has none, so its outage is not waited out
        with mock.patch.object(u, "LATITUDE", 60.0), mock.patch.object(u, "LONGITUDE", 10.0):
            u.update_once()
        self.metno_fetch.side_effect = RuntimeError("MET Norway HTTP 503")
        payload = u.update_once(FJORDVIK, u.LocationState())
        self.assertEqual((payload["status"], payload["sources"]["weather"]["id"]), ("ok", "openmeteo"))

    def test_a_failed_alerts_lookup_keeps_that_places_alerts(self):
        state = u.LocationState()
        self.metno_alerts.return_value = [ALERT]
        u.update_once(FJORDVIK, state)
        self.metno_alerts.side_effect = RuntimeError("MetAlerts HTTP 500")
        payload = u.update_once(FJORDVIK, state)
        self.assertEqual(payload["alerts"], [ALERT])
        self.assertEqual(payload["status"], "degraded")

    def test_the_kept_payload_is_a_copy(self):
        state = u.LocationState()
        u.update_once(DRY_HOLLOW, state)["current"]["temperature"] = -999
        self.assertNotEqual(state.read()["current"]["temperature"], -999)
        state.read()["current"]["temperature"] = -999
        self.assertNotEqual(state.read()["current"]["temperature"], -999)

    def test_coordinates_are_not_logged(self):
        u.update_once(DRY_HOLLOW, u.LocationState())
        printed = " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)
        self.assertNotIn("135", printed)
        self.assertIn("another place", printed)


if __name__ == "__main__":
    unittest.main()
