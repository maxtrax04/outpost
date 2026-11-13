"""MET Norway's warnings (MetAlerts) for Norway: parsing, the Norway check, and the alerts order."""

import unittest
from unittest import mock

import helpers
from helpers import load_fixture

import outpost_updater as u
import regions
from providers import metno
from test_updater import UpdaterTestCase, metno_data, openmeteo_data

# Public places, only to check the borders (none of them is anyone's location)
NORWAY = {
    "Oslo": (59.91, 10.75), "Bergen": (60.39, 5.32), "Stavanger": (58.97, 5.73), "Lindesnes": (57.98, 7.05),
    "Hvaler": (59.05, 11.0), "Halden": (59.12, 11.39), "Ørje": (59.48, 11.65), "Magnor": (59.95, 12.2),
    "Kongsvinger": (60.19, 12.0), "Trysil": (61.31, 12.27), "Drevsjø": (61.89, 12.05), "Røros": (62.57, 11.38),
    "Trondheim": (63.43, 10.39), "Meråker": (63.42, 11.74), "Nordli": (64.45, 13.6), "Mo i Rana": (66.31, 14.14),
    "Bodø": (67.28, 14.40), "Sulitjelma": (67.13, 16.08), "Narvik": (68.44, 17.43), "Tromsø": (69.65, 18.96),
    "Alta": (69.97, 23.27), "Kautokeino": (69.01, 23.04), "Karasjok": (69.47, 25.51), "Tana bru": (70.2, 28.18),
    "Neiden": (69.70, 29.38), "Svanvik": (69.45, 30.04), "Kirkenes": (69.73, 30.05), "Vardø": (70.37, 31.11),
    "Hammerfest": (70.66, 23.68), "Longyearbyen": (78.22, 15.65), "Jan Mayen": (70.98, -8.5),
}
NOT_NORWAY = {
    "Strömstad": (58.94, 11.17), "Töcksfors": (59.51, 11.84), "Charlottenberg": (59.88, 12.29),
    "Sälen": (61.16, 13.27), "Idre": (61.86, 12.72), "Funäsdalen": (62.54, 12.55), "Storlien": (63.32, 12.10),
    "Åre": (63.40, 13.08), "Östersund": (63.18, 14.64), "Gäddede": (64.50, 14.15), "Hemavan": (65.81, 15.09),
    "Abisko": (68.35, 18.83), "Kiruna": (67.86, 20.23), "Kilpisjärvi": (69.05, 20.79), "Hetta": (68.38, 23.63),
    "Karigasniemi": (69.40, 25.85), "Utsjoki": (69.91, 27.03), "Nuorgam": (70.08, 27.88),
    "Sevettijärvi": (69.52, 28.62), "Näätämö": (69.67, 29.03), "Nikel": (69.41, 30.22), "Rybachy": (69.85, 32.0),
    "Murmansk": (68.97, 33.08), "Skagen": (57.72, 10.58), "Gothenburg": (57.71, 11.97), "Lerwick": (60.15, -1.15),
    "Tórshavn": (62.01, -6.77), "Reykjavík": (64.15, -21.94), "Helsinki": (60.17, 24.94), "Stockholm": (59.33, 18.07),
}


class NorwayTests(unittest.TestCase):
    def test_places_in_norway(self):
        for name, place in NORWAY.items():
            with self.subTest(place=name):
                self.assertTrue(regions.in_norway(*place))

    def test_places_just_across_the_border(self):
        for name, place in NOT_NORWAY.items():
            with self.subTest(place=name):
                self.assertFalse(regions.in_norway(*place))

    def test_norway_is_inside_the_nordic_area(self):
        for name, place in NORWAY.items():
            with self.subTest(place=name):
                self.assertTrue(regions.in_nordic_countries(*place))


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.alerts = metno.build_alerts(load_fixture("metalerts.json"))

    def test_most_serious_first_without_tests_cancellations_or_repeats(self):
        self.assertEqual([a["title"] for a in self.alerts], ["Storm surge", "Heavy rain", "Blowing snow"])

    def test_severity_from_the_warning_or_its_colour(self):
        self.assertEqual([a["severity"] for a in self.alerts], ["extreme", "severe", "moderate"])

    def test_fields(self):
        snow = self.alerts[2]
        self.assertTrue(snow["description"].startswith("Parts of the mountins in Southern Norway: Local blowing snow"))
        self.assertEqual(snow["expires"], "2026-11-15T08:00:00+00:00")
        self.assertTrue(snow["uri"].startswith("https://www.met.no/"))

    def test_without_a_description_the_consequences_are_used(self):
        surge = self.alerts[0]
        self.assertEqual(surge["description"], "Example coast: Flooding of low-lying areas near the sea.")
        self.assertIsNone(surge["expires"])  # no end time given
        self.assertIsNone(surge["uri"])  # not a web link

    def test_no_warnings(self):
        for raw in ({}, {"features": None}, {"features": []}, {"features": [None, {}]}):
            with self.subTest(raw=raw):
                self.assertEqual(metno.build_alerts(raw), [])

    def test_request(self):
        with mock.patch.object(metno, "_get_json", return_value=load_fixture("metalerts.json")) as get:
            metno.fetch_alerts(59.912345, 10.75, "Outpost/1")
        url = get.call_args[0][0]
        self.assertTrue(url.startswith("https://api.met.no/weatherapi/metalerts/2.0/current.json?"))
        self.assertIn("lat=59.9123", url)
        self.assertIn("lang=en", url)
        self.assertIn("geographicDomain=land", url)
        self.assertEqual(get.call_args[0][1], "Outpost/1")


class OrderTests(UpdaterTestCase):
    WARNING = [{"title": "Heavy rain", "description": "", "severity": "severe", "expires": None, "uri": None}]

    def run_update(self, place, alerts_provider="auto", provider="metno", key=""):
        self.metno_alerts.return_value = self.WARNING
        with mock.patch.object(u, "PROVIDER", provider), mock.patch.object(u, "ALERTS_PROVIDER", alerts_provider), \
                mock.patch.object(u, "PIRATEWEATHER_API_KEY", key), \
                mock.patch.object(u, "LATITUDE", place[0]), mock.patch.object(u, "LONGITUDE", place[1]), \
                mock.patch.object(u.metno, "fetch", return_value=metno_data()), \
                mock.patch.object(u.openmeteo, "fetch", return_value=openmeteo_data()):
            u.update_once()
        return self.output()

    def printed(self):
        return " ".join(str(arg) for call in self.print.call_args_list for arg in call.args)

    def test_auto_in_norway_uses_met_norway_warnings(self):
        for provider in ("metno", "openmeteo", "auto"):
            with self.subTest(provider=provider):
                data = self.run_update(NORWAY["Bergen"], provider=provider, key="k")
                self.assertEqual(data["sources"]["alerts"], {"id": "metno", "name": "MET Norway (met.no)"})
                self.assertEqual(data["alerts"], self.WARNING)
        self.nws_alerts.assert_not_called()
        self.pirate_alerts.assert_not_called()

    def test_auto_elsewhere_in_the_nordic_countries_does_not_ask_met_norway(self):
        data = self.run_update(NOT_NORWAY["Östersund"])
        self.metno_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])

    def test_metno_can_be_chosen_in_norway(self):
        data = self.run_update(NORWAY["Tromsø"], alerts_provider="metno", provider="openmeteo")
        self.assertEqual(data["sources"]["alerts"]["id"], "metno")

    def test_choosing_metno_outside_norway_warns_once(self):
        self.run_update(NOT_NORWAY["Stockholm"], alerts_provider="metno")
        data = self.run_update(NOT_NORWAY["Stockholm"], alerts_provider="metno")
        self.metno_alerts.assert_not_called()
        self.assertIsNone(data["sources"]["alerts"])
        self.assertEqual(self.printed().count("OUTPOST_ALERTS_PROVIDER=metno"), 1)

    def test_a_failed_lookup_keeps_the_last_warnings(self):
        self.run_update(NORWAY["Oslo"])
        self.metno_alerts.side_effect = RuntimeError("MET Norway HTTP 503")
        data = self.run_update(NORWAY["Oslo"])
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["alerts"], self.WARNING)
        self.assertIsNotNone(data["current"]["temperature"])


if __name__ == "__main__":
    unittest.main()
