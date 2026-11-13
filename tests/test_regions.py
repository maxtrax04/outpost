"""Regions for OUTPOST_PROVIDER=auto (app/regions.py), and how auto uses them."""

import unittest
from unittest import mock

import helpers

import outpost_updater as u
import regions
from providers import nws
from test_updater import UpdaterTestCase, metno_data, nws_data, openmeteo_data

# Public places, only to check the borders (none of them is anyone's location)
NORDIC = {
    "Oslo": (59.91, 10.75), "Bergen": (60.39, 5.32), "Tromsø": (69.65, 18.96), "Kirkenes": (69.73, 30.05),
    "Nordkapp": (71.17, 25.78), "Stockholm": (59.33, 18.07), "Malmö": (55.60, 13.00), "Kiruna": (67.86, 20.23),
    "Visby": (57.64, 18.30), "Helsinki": (60.17, 24.94), "Mariehamn": (60.10, 19.94), "Imatra": (61.17, 28.77),
    "Joensuu": (62.60, 29.76), "Kuusamo": (65.97, 29.19), "Ivalo": (68.66, 27.54), "Copenhagen": (55.68, 12.57),
    "Esbjerg": (55.47, 8.45), "Skagen": (57.72, 10.58), "Rønne": (55.10, 14.70), "Gedser": (54.57, 11.93),
    "Reykjavík": (64.15, -21.94), "Akureyri": (65.68, -18.09), "Tórshavn": (62.01, -6.77),
    "Longyearbyen": (78.22, 15.65),
}
NOT_NORDIC = {
    "Hamburg": (53.55, 10.00), "Kiel": (54.32, 10.13), "Berlin": (52.52, 13.40), "Gdańsk": (54.35, 18.65),
    "Kaliningrad": (54.71, 20.51), "Klaipėda": (55.70, 21.13), "Riga": (56.95, 24.11), "Tallinn": (59.44, 24.75),
    "Saint Petersburg": (59.94, 30.31), "Vyborg": (60.71, 28.75), "Petrozavodsk": (61.79, 34.35),
    "Kostomuksha": (64.57, 30.60), "Murmansk": (68.97, 33.08), "Edinburgh": (55.95, -3.19),
    "Lerwick": (60.15, -1.15), "Nuuk": (64.18, -51.72), "Amsterdam": (52.37, 4.90), "Las Vegas": (36.17, -115.14),
    "Sydney": (-33.87, 151.21),
}


class NordicTests(unittest.TestCase):
    def test_places_in_the_nordic_countries(self):
        for name, (latitude, longitude) in NORDIC.items():
            with self.subTest(place=name):
                self.assertTrue(regions.in_nordic_countries(latitude, longitude))

    def test_places_outside(self):
        for name, (latitude, longitude) in NOT_NORDIC.items():
            with self.subTest(place=name):
                self.assertFalse(regions.in_nordic_countries(latitude, longitude))


class AutoTests(UpdaterTestCase):
    def run_auto(self, latitude, longitude):
        with mock.patch.object(u, "PROVIDER", "auto"), mock.patch.object(u, "LATITUDE", latitude), \
                mock.patch.object(u, "LONGITUDE", longitude), \
                mock.patch.object(u.metno, "fetch", return_value=metno_data()) as metno_fetch, \
                mock.patch.object(u.nws, "fetch", side_effect=nws.NoCoverageError("US only")) as nws_fetch, \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()) as openmeteo_fetch:
            u.update_once()
        return self.output(), metno_fetch, nws_fetch, openmeteo_fetch

    def test_nordic_countries_use_met_norway(self):
        data, metno_fetch, nws_fetch, _ = self.run_auto(*NORDIC["Oslo"])
        self.assertEqual((data["provider"], data["sources"]["weather"]["id"]), ("auto", "metno"))
        metno_fetch.assert_called_once()
        nws_fetch.assert_not_called()

    def test_met_norway_gaps_are_filled_from_open_meteo(self):
        data, _, _, openmeteo_fetch = self.run_auto(*NORDIC["Oslo"])
        openmeteo_fetch.assert_called_once()
        self.assertEqual(data["sources"]["fill"]["id"], "openmeteo")
        self.assertIn("current.visibility", data["sources"]["fill"]["fields"])
        self.assertIsNotNone(data["current"]["visibility"])
        self.assertEqual(data["current"]["condition"], "Fair")  # MET Norway's own wording is kept

    def test_nordic_locations_are_not_sent_to_nws_for_alerts(self):
        data, _, _, _ = self.run_auto(*NORDIC["Helsinki"])
        self.nws_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_choosing_nws_alerts_in_a_nordic_country_warns_once_without_asking_nws(self):
        with mock.patch.object(u, "ALERTS_PROVIDER", "nws"):
            self.run_auto(*NORDIC["Reykjavík"])
            data, _, _, _ = self.run_auto(*NORDIC["Reykjavík"])
        self.nws_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])
        printed = " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)
        self.assertEqual(printed.count("OUTPOST_ALERTS_PROVIDER=nws"), 1)

    def test_elsewhere_auto_is_unchanged(self):
        data, metno_fetch, nws_fetch, _ = self.run_auto(*NOT_NORDIC["Hamburg"])
        metno_fetch.assert_not_called()
        nws_fetch.assert_called_once()
        self.assertEqual(data["sources"]["weather"]["id"], "openmeteo")

    def test_the_us_still_uses_nws(self):
        with mock.patch.object(u, "PROVIDER", "auto"), mock.patch.object(u, "LATITUDE", 39.0), \
                mock.patch.object(u, "LONGITUDE", -98.0), mock.patch.object(u.metno, "fetch") as metno_fetch, \
                mock.patch.object(u.nws, "fetch", return_value=nws_data()), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        metno_fetch.assert_not_called()
        self.assertEqual(self.output()["sources"]["weather"]["id"], "nws")

    def test_met_norway_failure_keeps_the_last_good_data(self):
        self.run_auto(*NORDIC["Oslo"])
        with mock.patch.object(u, "PROVIDER", "auto"), mock.patch.object(u, "LATITUDE", 59.91), \
                mock.patch.object(u, "LONGITUDE", 10.75), \
                mock.patch.object(u.metno, "fetch", side_effect=RuntimeError("MET Norway HTTP 503")):
            u.update_once()
        self.assertEqual(self.output()["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
