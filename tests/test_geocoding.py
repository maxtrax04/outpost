"""Place search (app/providers/geocoding.py) and /api/places (app/outpost_server.py)."""

import io
import json
import unittest
import urllib.error
from unittest import mock

import helpers  # noqa: F401  (puts app/ on the path)

import outpost_server as s
import outpost_updater as u
from providers import geocoding

# A made-up answer in Open-Meteo's geocoding format
ANSWER = {"results": [
    {"name": "Cinder Flats", "latitude": 41.5, "longitude": -101.25, "country": "Exampleland",
     "admin1": "North Province", "timezone": "America/Chicago", "population": 1200},
    {"name": "Cinder Flats", "latitude": -12.0, "longitude": 130.0, "country": "Otherland"},
    {"name": "", "latitude": 1.0, "longitude": 1.0},
    {"name": "Nowhere", "latitude": "north", "longitude": 1.0},
    {"name": "Off The Map", "latitude": 95.0, "longitude": 1.0},
    "not a place",
]}


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def answer(body=ANSWER):
    return Response(json.dumps(body).encode())


class GeocodingTestCase(unittest.TestCase):
    def setUp(self):
        geocoding._cache.clear()
        geocoding._last_request[0] = 0.0
        self.addCleanup(geocoding._cache.clear)
        self.clock = Clock()

    def search(self, text="Cinder Flats"):
        return geocoding.search(text, "test-agent", clock=self.clock, sleep=self.clock.sleep)


class ParseTests(unittest.TestCase):
    def test_only_usable_places_are_kept(self):
        self.assertEqual(geocoding.parse(ANSWER), [
            {"name": "Cinder Flats", "region": "North Province", "country": "Exampleland",
             "latitude": 41.5, "longitude": -101.25, "timezone": "America/Chicago"},
            {"name": "Cinder Flats", "region": "", "country": "Otherland",
             "latitude": -12.0, "longitude": 130.0, "timezone": ""},
        ])

    def test_nothing_found(self):
        for raw in ({}, {"generationtime_ms": 0.5}, {"results": None}, [], None):
            self.assertEqual(geocoding.parse(raw), [])

    def test_at_most_eight(self):
        many = {"results": [{"name": f"Place {i}", "latitude": 1.0, "longitude": float(i)} for i in range(20)]}
        self.assertEqual(len(geocoding.parse(many)), geocoding.MAX_RESULTS)

    def test_queries_are_one_tidy_line(self):
        self.assertEqual(geocoding.clean_query("  Cinder\n\tFlats  "), "Cinder Flats")
        self.assertEqual(geocoding.clean_query(None), "")


class SearchTests(GeocodingTestCase):
    def test_the_request(self):
        with mock.patch("urllib.request.urlopen", return_value=answer()) as urlopen:
            self.search("Cinder Flats")
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.startswith(geocoding.API_URL + "?"))
        self.assertIn("name=Cinder+Flats", request.full_url)
        self.assertIn("count=8", request.full_url)
        self.assertEqual(request.get_header("User-agent"), "test-agent")

    def test_a_search_is_cached_for_a_day_whatever_its_case(self):
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: answer()) as urlopen:
            first = self.search("Cinder Flats")
            first[0]["name"] = "changed"
            self.assertEqual(self.search("cinder flats")[0]["name"], "Cinder Flats")
            self.assertEqual(urlopen.call_count, 1)
            self.clock.now += geocoding.CACHE_SECONDS
            self.search("Cinder Flats")
            self.assertEqual(urlopen.call_count, 2)

    def test_at_most_one_search_a_second(self):
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: answer()):
            self.search("Cinder Flats")
            self.clock.now += 0.25
            self.search("Dry Hollow")
        self.assertEqual(self.clock.slept, [0.75])

    def test_old_searches_are_dropped_past_the_limit(self):
        with mock.patch.object(geocoding, "MAX_CACHED", 3), \
                mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: answer()):
            for name in ("aa", "bb", "cc", "dd"):
                self.search(name)
        self.assertEqual(list(geocoding._cache), ["bb", "cc", "dd"])

    def test_failures_are_not_cached_and_do_not_quote_the_search(self):
        failures = (urllib.error.HTTPError("url", 503, "Busy", {}, None), urllib.error.URLError("down"),
                    TimeoutError("slow"))
        for failure in failures:
            with self.subTest(failure=failure), mock.patch("urllib.request.urlopen", side_effect=failure), \
                    self.assertRaises(RuntimeError) as caught:
                self.search("Secret Cabin")
            self.assertNotIn("Secret", str(caught.exception))
        self.assertEqual(geocoding._cache, {})
        with mock.patch("urllib.request.urlopen", return_value=Response(b"not json")), \
                self.assertRaises(RuntimeError):
            self.search("Cinder Flats")


class PlacesEndpointTests(GeocodingTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(u, "LOCATION_SEARCH", True).start()

    def test_an_answer(self):
        with mock.patch("urllib.request.urlopen", return_value=answer()):
            body = s.search_places({"q": ["  Cinder  Flats "]})
        self.assertEqual(body["source"], {"id": "openmeteo", "name": "Open-Meteo.com"})
        self.assertEqual([place["country"] for place in body["places"]], ["Exampleland", "Otherland"])

    def test_queries_of_2_to_100_characters(self):
        for text in ("", " a ", "x" * 101):
            with self.subTest(text=text), self.assertRaises(s.ApiError) as caught:
                s.search_places({"q": [text]})
            self.assertEqual((caught.exception.status, caught.exception.code), (400, "bad_query"))
        with self.assertRaises(s.ApiError):
            s.search_places({})

    def test_off(self):
        with mock.patch.object(u, "LOCATION_SEARCH", False), self.assertRaises(s.ApiError) as caught, \
                mock.patch("urllib.request.urlopen") as urlopen:
            s.search_places({"q": ["Cinder Flats"]})
        self.assertEqual(caught.exception.status, 403)
        urlopen.assert_not_called()

    def test_a_failed_search_is_a_502_logged_without_the_text(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr, \
                self.assertRaises(s.ApiError) as caught:
            s.search_places({"q": ["Secret Cabin"]})
        self.assertEqual((caught.exception.status, caught.exception.code), (502, "search_failed"))
        self.assertIn("place search failed", stderr.getvalue())
        self.assertNotIn("Secret", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
