"""OUTPOST_PROVIDER=auto when MET Norway or NWS is down: Pirate Weather, then Open-Meteo once the data is stale."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers

import outpost_updater as u
from test_pirateweather import pirate_data
from test_updater import UpdaterTestCase, metno_data, openmeteo_data

OSLO = (59.91, 10.75)


class OutageTests(UpdaterTestCase):
    def update(self, metno_ok=True, open_meteo_ok=True, key="", pirate_ok=True):
        metno = {"return_value": metno_data()} if metno_ok else {"side_effect": RuntimeError("MET Norway HTTP 503")}
        open_meteo = ({"return_value": openmeteo_data()} if open_meteo_ok
                      else {"side_effect": RuntimeError("Open-Meteo unreachable")})
        pirate = {"return_value": pirate_data()} if pirate_ok else {"side_effect": RuntimeError("Pirate Weather HTTP 500")}
        with mock.patch.object(u, "PROVIDER", "auto"), mock.patch.object(u, "PIRATEWEATHER_API_KEY", key), \
                mock.patch.object(u, "LATITUDE", OSLO[0]), mock.patch.object(u, "LONGITUDE", OSLO[1]), \
                mock.patch.object(u.metno, "fetch", **metno), \
                mock.patch.object(u.openmeteo, "fetch", **open_meteo) as open_meteo_fetch, \
                mock.patch.object(u.pirateweather, "fetch", **pirate):
            u.update_once()
        return self.output(), open_meteo_fetch

    def age_saved_data(self, seconds):
        """Make the saved weather.json look as if its data was fetched `seconds` ago."""
        path = self.data_dir / "weather.json"
        data = json.loads(path.read_text())
        data["generated_at"] = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        path.write_text(json.dumps(data))

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)

    def test_a_short_outage_keeps_the_last_good_data(self):
        self.update()
        data, open_meteo_fetch = self.update(metno_ok=False)
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("degraded", "metno"))
        self.assertNotIn("using Open-Meteo", self.printed())

    def test_once_the_data_is_stale_open_meteo_takes_over(self):
        self.update()
        self.age_saved_data(u.stale_after_seconds() + 1)
        data, _ = self.update(metno_ok=False)
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "openmeteo"))
        self.assertIsNone(data["last_error"])
        self.assertIn("MET Norway failed (MET Norway HTTP 503); using Open-Meteo until it is back", self.printed())

    def test_it_stays_on_open_meteo_until_the_specialist_is_back(self):
        self.update()
        self.age_saved_data(u.stale_after_seconds() + 1)
        self.update(metno_ok=False)
        data, _ = self.update(metno_ok=False)  # the Open-Meteo data is fresh, but it does not go back to degraded
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "openmeteo"))
        data, _ = self.update()
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "metno"))

    def test_not_stale_until_three_missed_updates(self):
        with mock.patch.object(u, "UPDATE_INTERVAL", 600):
            self.assertEqual(u.stale_after_seconds(), 1800)
            self.update()
            self.age_saved_data(1700)
            self.assertEqual(self.update(metno_ok=False)[0]["status"], "degraded")
        with mock.patch.object(u, "UPDATE_INTERVAL", 30):
            self.assertEqual(u.stale_after_seconds(), 300)  # never sooner than 5 minutes, like the dashboard

    def test_with_no_saved_data_open_meteo_is_used_at_once(self):
        data, _ = self.update(metno_ok=False)
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "openmeteo"))

    def test_if_open_meteo_fails_too_the_last_good_data_stays(self):
        self.update()
        self.age_saved_data(u.stale_after_seconds() + 1)
        data, _ = self.update(metno_ok=False, open_meteo_ok=False)
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("degraded", "metno"))
        self.assertEqual(data["last_error"], "MET Norway HTTP 503")

    def test_with_a_key_pirate_weather_comes_before_open_meteo(self):
        self.update(key="k")
        data, open_meteo_fetch = self.update(metno_ok=False, key="k")
        self.assertEqual(data["sources"]["weather"]["id"], "pirateweather")
        self.assertNotIn("using Open-Meteo", self.printed())

    def test_with_a_key_that_fails_open_meteo_still_waits_for_stale_data(self):
        self.update(key="k")
        data, _ = self.update(metno_ok=False, key="k", pirate_ok=False)
        self.assertEqual(data["status"], "degraded")
        self.age_saved_data(u.stale_after_seconds() + 1)
        data, _ = self.update(metno_ok=False, key="k", pirate_ok=False)
        self.assertEqual((data["status"], data["sources"]["weather"]["id"]), ("ok", "openmeteo"))


if __name__ == "__main__":
    unittest.main()
