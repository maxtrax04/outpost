"""The API server (app/outpost_server.py): parsing, the per-place cache and limits, and the HTTP answers."""

import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT

import outpost_server as s
import outpost_updater as u


def query(**values):
    return {name: [value] for name, value in values.items()}


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class FakeUpdates:
    """Stands in for update_once: records each fetch and answers with a numbered payload."""

    def __init__(self):
        self.calls = []

    def __call__(self, location, state):
        self.calls.append((location.latitude, location.longitude))
        payload = {"location": location.name, "coordinates": {"latitude": location.latitude,
                                                              "longitude": location.longitude},
                   "fetch": len(self.calls)}
        state.write(payload)
        return payload


class ParsingTests(unittest.TestCase):
    def test_coordinates_are_rounded_to_about_a_kilometer(self):
        self.assertEqual(s.coordinate(query(lat="59.91394"), "lat", 90), 59.91)
        self.assertEqual(s.coordinate(query(lon="-115.43281"), "lon", 180), -115.43)

    def test_minus_zero_is_zero(self):
        value = s.coordinate(query(lat="-0.001"), "lat", 90)
        self.assertEqual(str(value), "0.0")

    def test_bad_coordinates_are_refused(self):
        for bad in ({}, query(lat=""), query(lat="north"), query(lat="91"), query(lat="-90.5"),
                    query(lat="nan"), query(lat="inf")):
            with self.subTest(bad=bad), self.assertRaises(s.ApiError) as caught:
                s.coordinate(bad, "lat", 90)
            self.assertEqual(caught.exception.status, 400)
        self.assertEqual(s.coordinate(query(lon="180"), "lon", 180), 180.0)

    def test_names_are_one_short_line_of_text(self):
        self.assertEqual(s.place_name(query(name="  Cinder   Flats ")), "Cinder Flats")
        self.assertEqual(s.place_name(query(name="Line\nbreak\x00here")), "Line break here")
        self.assertEqual(len(s.place_name(query(name="x" * 500))), s.MAX_NAME_LENGTH)
        self.assertEqual(s.place_name({}), s.DEFAULT_PLACE_NAME)
        self.assertEqual(s.place_name(query(name="\t ")), s.DEFAULT_PLACE_NAME)


class PlacesTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.updates = FakeUpdates()
        self.places = s.Places(limit=3, refresh_seconds=900, clock=self.clock, update=self.updates)

    def test_a_place_is_fetched_once_then_reused(self):
        self.assertEqual(self.places.weather(1.0, 2.0)["fetch"], 1)
        self.clock.now += 899
        self.assertEqual(self.places.weather(1.0, 2.0)["fetch"], 1)
        self.clock.now += 1
        self.assertEqual(self.places.weather(1.0, 2.0)["fetch"], 2)
        self.assertEqual(self.updates.calls, [(1.0, 2.0), (1.0, 2.0)])

    def test_the_update_gets_the_fixed_name_and_its_own_state(self):
        self.places.weather(1.0, 2.0)
        self.assertEqual(self.places._places[(1.0, 2.0)].state.read()["location"], s.DEFAULT_PLACE_NAME)
        self.assertIsNot(self.places._places[(1.0, 2.0)].location, u.home_location())
        self.assertFalse(self.places._places[(1.0, 2.0)].location.home)

    def test_a_new_place_over_the_limit_is_refused_and_not_kept(self):
        for lat in (1.0, 2.0, 3.0):
            self.places.weather(lat, 0.0)
        with self.assertRaises(s.ApiError) as caught:
            self.places.weather(4.0, 0.0)
        self.assertEqual((caught.exception.status, caught.exception.code), (429, "location_limit"))
        self.assertNotIn((4.0, 0.0), self.places._places)

    def test_refreshes_count_and_over_the_limit_the_last_data_is_reused(self):
        self.places.weather(1.0, 0.0)
        self.places.weather(2.0, 0.0)
        self.clock.now += 900
        self.assertEqual(self.places.weather(1.0, 0.0)["fetch"], 3)   # the third fetch this hour
        self.assertEqual(self.places.weather(2.0, 0.0)["fetch"], 2)   # due, but the limit is used up
        self.assertEqual(len(self.updates.calls), 3)

    def test_the_limit_is_a_rolling_hour(self):
        for lat in (1.0, 2.0, 3.0):
            self.places.weather(lat, 0.0)
        self.clock.now += s.LIMIT_WINDOW_SECONDS
        self.assertEqual(self.places.weather(4.0, 0.0)["fetch"], 4)

    def test_a_limit_of_zero_allows_no_other_places(self):
        places = s.Places(limit=0, clock=self.clock, update=self.updates)
        with self.assertRaises(s.ApiError):
            places.weather(1.0, 0.0)
        self.assertEqual(self.updates.calls, [])

    def test_a_place_nobody_asks_for_is_forgotten_after_an_hour(self):
        self.places.limit = 100
        self.places.weather(1.0, 0.0)
        self.clock.now += s.FORGET_AFTER_SECONDS + 1
        self.places.weather(2.0, 0.0)
        self.assertNotIn((1.0, 0.0), self.places._places)

    def test_at_most_max_places_are_kept_dropping_the_least_recently_seen(self):
        self.places.limit = 1000
        for index in range(s.MAX_PLACES + 5):
            self.clock.now += 1
            self.places.weather(float(index % 90), float(index))
        self.assertEqual(len(self.places), s.MAX_PLACES)
        self.assertNotIn((0.0, 0.0), self.places._places)

    def test_answers_are_copies(self):
        self.places.weather(1.0, 2.0)["fetch"] = -1
        self.assertEqual(self.places.weather(1.0, 2.0)["fetch"], 1)


class HttpTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data_path = Path(folder.name) / "weather.json"
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(u, "DATA_PATH", self.data_path).start()
        mock.patch.object(u, "LOCATION_SEARCH", True).start()
        self.updates = FakeUpdates()
        self.places = s.Places(limit=5, update=self.updates)
        server = s.make_server(self.places, port=0)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as response:
                return response.status, dict(response.headers), json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), json.load(error)

    def test_status(self):
        status, headers, body = self.get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"api_version": 1, "version": u.APP_VERSION, "location_search": True})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(headers["Content-Type"].startswith("application/json"))

    def test_home_is_weather_json(self):
        saved = {"schema_version": 1, "location": "Test Site", "status": "ok"}
        self.data_path.write_text(json.dumps(saved))
        self.assertEqual(self.get("/api/weather")[2], saved)
        self.assertEqual(self.updates.calls, [])

    def test_home_before_the_first_update_is_an_error_payload(self):
        status, _, body = self.get("/api/weather")
        self.assertEqual((status, body["status"], body["schema_version"]), (200, "error", 1))

    def test_another_place_has_the_name_asked_for(self):
        status, headers, body = self.get("/api/weather?lat=12.3456&lon=-45.6789&name=Cinder%20Flats")
        self.assertEqual(status, 200)
        self.assertEqual(body["location"], "Cinder Flats")
        self.assertEqual(body["coordinates"], {"latitude": 12.35, "longitude": -45.68})
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_bad_requests(self):
        for path in ("/api/weather?lat=10", "/api/weather?lon=10", "/api/weather?lat=100&lon=0",
                     "/api/weather?lat=a&lon=b"):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual((status, body["error"]), (400, "bad_location"))
        self.assertEqual(self.get("/api/nothing")[0], 404)
        self.assertEqual(self.get("/api/status/")[0], 404)

    def test_other_places_can_be_turned_off(self):
        with mock.patch.object(u, "LOCATION_SEARCH", False):
            status, _, body = self.get("/api/weather?lat=1&lon=2")
            self.assertEqual((status, body["error"]), (403, "location_search_off"))
            self.assertFalse(self.get("/api/status")[2]["location_search"])
            self.assertEqual(self.get("/api/weather")[0], 200)  # home still works
        self.assertEqual(self.updates.calls, [])

    def test_the_limit_answers_429(self):
        for lat in range(5):
            self.assertEqual(self.get(f"/api/weather?lat={lat}&lon=0")[0], 200)
        status, _, body = self.get("/api/weather?lat=9&lon=0")
        self.assertEqual((status, body["error"]), (429, "location_limit"))

    def test_an_unexpected_error_is_a_500_and_the_server_keeps_going(self):
        self.places.update = lambda *args: 1 / 0
        with mock.patch("builtins.print"):
            self.assertEqual(self.get("/api/weather?lat=1&lon=1")[0], 500)
        self.assertEqual(self.get("/api/status")[0], 200)

    def test_head_has_the_headers_without_a_body(self):
        request = urllib.request.Request(self.base + "/api/status", method="HEAD")
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.read(), b"")

    def test_requests_are_not_logged(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.get("/api/weather?lat=12.34&lon=56.78")
            self.get("/api/nothing")
        self.assertEqual(stderr.getvalue(), "")


class ServerSetupTests(unittest.TestCase):
    def test_start_runs_the_server_instead_of_the_old_loop(self):
        start = (ROOT / "app" / "start.sh").read_text(encoding="utf-8")
        self.assertIn("python3 /app/outpost_server.py &", start)
        self.assertNotIn("--loop", start)
        # The first update still runs before nginx starts
        self.assertLess(start.index("python3 /app/outpost_updater.py"), start.index("exec nginx"))

    def test_nginx_proxies_the_api_with_a_rate_limit(self):
        conf = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
        self.assertIn("limit_req_zone $binary_remote_addr zone=outpost_api:1m rate=5r/s;", conf)
        block = conf[conf.index("location /api/ {"):]
        block = block[:block.index("}")]
        self.assertIn(f"proxy_pass http://{s.HOST}:{s.PORT};", block)
        self.assertIn("limit_req zone=outpost_api burst=20 nodelay;", block)
        self.assertIn("limit_req_status 429;", block)
        # Viewers' coordinates are in the request addresses
        self.assertIn("access_log off;", block)
        self.assertIn("error_log /var/log/nginx/error.log crit;", block)

    def test_places_refresh_no_more_often_than_open_meteo_allows(self):
        self.assertGreaterEqual(s.PLACE_REFRESH_SECONDS, u.openmeteo.MIN_REQUEST_SECONDS)
        self.assertGreaterEqual(s.PLACE_REFRESH_SECONDS, u.UPDATE_INTERVAL)


if __name__ == "__main__":
    unittest.main()
