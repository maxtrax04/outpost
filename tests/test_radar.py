"""Rain radar for the map (app/outpost_radar.py, /api/radar and /tiles/radar/ in app/outpost_server.py)."""

import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import helpers  # noqa: F401  (puts app/ on the path)

import outpost_radar as r
import outpost_server as s
import outpost_updater as u
import regions

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
BASE = 1_800_000_000  # 2027-01-15T08:00:00Z


def stamp(seconds):
    return r.iso_time(seconds).replace("Z", ".000Z")


def capabilities(times):
    listed = ",".join(stamp(t) for t in times)
    return (f'<WMS_Capabilities><Layer><Dimension name="time" default="{stamp(times[-1])}" units="ISO8601" '
            f'nearestValue="1">{listed}</Dimension></Layer></WMS_Capabilities>').encode()


def rainviewer_index(times, host="https://tilecache.rainviewer.com"):
    return json.dumps({"version": "2.0", "host": host, "radar": {
        "past": [{"time": t, "path": f"/v2/radar/{t:x}"} for t in times], "nowcast": []}}).encode()


class Clock:
    def __init__(self):
        self.now = float(BASE + 7200)

    def __call__(self):
        return self.now


class Lists:
    """A stand-in for the radar services' frame lists."""

    def __init__(self):
        # NOAA every 2 minutes for 2.5 hours; RainViewer every 10 minutes for 2 hours
        self.noaa = [BASE - 1800 + 120 * i for i in range(76)]
        self.rainviewer = [BASE + 600 * i for i in range(13)]
        self.urls = []
        self.fail = False

    def __call__(self, url):
        self.urls.append(url)
        if self.fail:
            raise r.RadarError("the radar service could not be reached (URLError)")
        if "rainviewer" in url:
            return "application/json", rainviewer_index(self.rainviewer)
        # Each NOAA area has its own times
        shift = 7 if "alaska" in url else 0
        return "text/xml", capabilities([t + shift for t in self.noaa])


class Tiles:
    def __init__(self, kind="image/png", body=PNG):
        self.urls, self.kind, self.body = [], kind, body

    def __call__(self, url):
        self.urls.append(url)
        return self.kind, self.body


def make_radar(zoom=7):
    lists, tiles, clock = Lists(), Tiles(), Clock()
    return r.Radar(zoom, "Outpost-test", list_get=lists, tile_get=tiles, clock=clock), lists, tiles, clock


class AreaTests(unittest.TestCase):
    def test_noaa_in_the_us(self):
        for latitude, longitude, area in ((39.0, -98.0, "conus"), (47.5, -122.3, "conus"), (25.8, -80.2, "conus"),
                                          (61.2, -149.9, "alaska"), (58.3, -134.4, "alaska"), (21.3, -157.8, "hawaii"),
                                          (13.5, 144.8, "guam"), (15.2, 145.7, "guam"), (18.4, -66.1, "carib")):
            with self.subTest(latitude=latitude, longitude=longitude):
                self.assertEqual(regions.noaa_radar_area(latitude, longitude), area)
                self.assertEqual(r.source_for(latitude, longitude), (r.NOAA, area))

    def test_rainviewer_elsewhere(self):
        # Europe, northern Mexico, Mexico City, the Bahamas, Cuba, Yukon, and the far south
        for latitude, longitude in ((48.9, 2.3), (25.7, -100.3), (19.4, -99.1), (25.0, -77.4), (23.1, -82.4),
                                    (60.7, -135.1), (-33.9, 151.2)):
            with self.subTest(latitude=latitude, longitude=longitude):
                self.assertIsNone(regions.noaa_radar_area(latitude, longitude))
                self.assertEqual(r.source_for(latitude, longitude), (r.RAINVIEWER, None))


class FrameTests(unittest.TestCase):
    def test_the_loop_is_a_frame_every_10_minutes_over_2_hours(self):
        frames = r.noaa_frames(capabilities(Lists().noaa).decode())
        times = [frame["time"] for frame in frames]
        self.assertEqual(times[-1], BASE - 1800 + 120 * 75)  # the latest
        self.assertEqual(len(frames), 13)
        self.assertTrue(all(b - a >= 570 for a, b in zip(times, times[1:])))
        self.assertLessEqual(times[-1] - times[0], r.LOOP_SECONDS)
        self.assertEqual(frames[-1]["id"], "20270115T100000Z")
        self.assertEqual(frames[-1]["upstream"], "2027-01-15T10:00:00Z")

    def test_noaa_without_times_is_an_error(self):
        for text in ("<WMS_Capabilities/>", '<Dimension name="time">nonsense</Dimension>'):
            with self.subTest(text=text), self.assertRaises(r.RadarError):
                r.noaa_frames(text)

    def test_rainviewer_frames(self):
        frames = r.rainviewer_frames(json.loads(rainviewer_index(Lists().rainviewer)))
        self.assertEqual(len(frames), 13)
        self.assertEqual(frames[-1]["upstream"], f"https://tilecache.rainviewer.com/v2/radar/{BASE + 7200:x}")

    def test_rainviewer_must_name_its_own_tile_server(self):
        for host in ("https://evil.example", "http://tilecache.rainviewer.com", "https://rainviewer.com.evil.example",
                     "https://tilecache.rainviewer.com/../x"):
            with self.subTest(host=host), self.assertRaises(r.RadarError):
                r.rainviewer_frames(json.loads(rainviewer_index([BASE], host)))

    def test_rainviewer_paths_are_checked(self):
        index = {"host": "https://tilecache.rainviewer.com",
                 "radar": {"past": [{"time": BASE, "path": "/v2/radar/../../x"}, {"time": "soon", "path": "/v2/radar/abc123"}]}}
        with self.assertRaises(r.RadarError):
            r.rainviewer_frames(index)


class TileAddressTests(unittest.TestCase):
    def test_noaa_asks_for_the_tile_square(self):
        url = r.noaa_tile_url("conus", "2027-01-15T10:00:00Z", 1, 0, 0)
        parts = urlsplit(url)
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}",
                         "https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows")
        query = {name: values[0] for name, values in parse_qs(parts.query, keep_blank_values=True).items()}
        self.assertEqual(query["BBOX"], "-20037508.34,0.00,0.00,20037508.34")  # the northwest quarter
        self.assertEqual((query["CRS"], query["LAYERS"], query["TIME"], query["TRANSPARENT"]),
                         ("EPSG:3857", "conus_bref_qcd", "2027-01-15T10:00:00Z", "true"))

    def test_rainviewer_tile(self):
        self.assertEqual(r.rainviewer_tile_url("https://tilecache.rainviewer.com/v2/radar/abc123", 7, 24, 49),
                         "https://tilecache.rainviewer.com/v2/radar/abc123/256/7/24/49/2/1_1.png")

    def test_paths(self):
        self.assertEqual(r.parse_tile_path("/tiles/radar/noaa/alaska/20270115T100000Z/7/10/20.png"),
                         (r.NOAA, "alaska", "20270115T100000Z", 7, 10, 20))
        self.assertEqual(r.parse_tile_path("/tiles/radar/rainviewer/abc123/7/1/2.png"),
                         (r.RAINVIEWER, None, "abc123", 7, 1, 2))
        for path in ("/tiles/radar/noaa/mars/x/7/1/2.png", "/tiles/radar/rainviewer/a-b/7/1/2.png",
                     "/tiles/radar/rainviewer/abc/7/1/2.jpg", "/tiles/radar/noaa/conus/7/1/2.png"):
            with self.subTest(path=path):
                self.assertIsNone(r.parse_tile_path(path))


class RadarTests(unittest.TestCase):
    def test_noaa_in_the_us(self):
        radar, lists, _, _ = make_radar(zoom=9)
        answer = radar.answer(39.0, -98.0)
        self.assertEqual((answer["source"], answer["credit"], answer["zoom"]), ("noaa", "NOAA", 9))
        self.assertEqual(len(answer["frames"]), 13)
        self.assertEqual(answer["frames"][-1], {"time": "2027-01-15T10:00:00Z",
                                                "tiles": "tiles/radar/noaa/conus/20270115T100000Z/{z}/{x}/{y}.png"})
        self.assertIn("conus/conus_bref_qcd/ows?service=WMS", lists.urls[0])

    def test_rainviewer_elsewhere_stops_at_zoom_7(self):
        radar, _, _, _ = make_radar(zoom=10)
        answer = radar.answer(48.9, 2.3)
        self.assertEqual((answer["source"], answer["credit"], answer["zoom"]), ("rainviewer", "RainViewer", 7))
        self.assertEqual(answer["frames"][-1]["tiles"], f"tiles/radar/rainviewer/{BASE + 7200:x}/{{z}}/{{x}}/{{y}}.png")
        self.assertTrue(answer["credit_url"].startswith("https://"))

    def test_lists_are_kept_for_two_minutes_and_used_while_a_service_is_down(self):
        radar, lists, _, clock = make_radar()
        radar.answer(48.9, 2.3)
        clock.now += r.FRAMES_CACHE_SECONDS - 1
        radar.answer(48.9, 2.3)
        self.assertEqual(len(lists.urls), 1)
        clock.now += 2
        lists.fail = True
        self.assertEqual(len(radar.answer(48.9, 2.3)["frames"]), 13)
        self.assertEqual(len(lists.urls), 2)
        clock.now += r.FRAME_KEEP_SECONDS
        with self.assertRaises(r.RadarError):
            radar.answer(48.9, 2.3)

    def test_a_listed_frame_is_fetched(self):
        radar, _, tiles, _ = make_radar()
        tile = radar.answer(39.0, -98.0)["frames"][-1]["tiles"].format(z=7, x=29, y=48)
        self.assertEqual(radar.tile("/" + tile), PNG)
        self.assertIn("conus_bref_qcd", tiles.urls[0])
        self.assertIn("TIME=2027-01-15T10%3A00%3A00Z", tiles.urls[0])

        tile = radar.answer(48.9, 2.3)["frames"][0]["tiles"].format(z=7, x=64, y=44)
        radar.tile("/" + tile)
        self.assertEqual(tiles.urls[1], f"https://tilecache.rainviewer.com/v2/radar/{BASE:x}/256/7/64/44/2/1_1.png")

    def test_only_listed_frames_at_the_map_zoom(self):
        radar, _, tiles, _ = make_radar()
        radar.answer(39.0, -98.0)
        for path in ("/tiles/radar/noaa/conus/20200101T000000Z/7/29/48.png",   # never listed
                     "/tiles/radar/noaa/conus/20270115T100000Z/8/29/48.png",   # another zoom
                     "/tiles/radar/noaa/conus/20270115T100000Z/7/128/48.png",  # beyond the world
                     "/tiles/radar/noaa/alaska/20270115T100000Z/7/29/48.png",  # another list's frame
                     "/tiles/radar/elsewhere/7/1/2.png"):
            with self.subTest(path=path), self.assertRaises(r.RadarNotFound):
                radar.tile(path)
        self.assertEqual(tiles.urls, [])

    def test_a_frame_is_forgotten_after_three_hours(self):
        radar, lists, _, clock = make_radar()
        tile = "/" + radar.answer(39.0, -98.0)["frames"][-1]["tiles"].format(z=7, x=29, y=48)
        clock.now += r.FRAME_KEEP_SECONDS + 1
        lists.noaa = [t + r.FRAME_KEEP_SECONDS + 600 for t in lists.noaa]
        with self.assertRaises(r.RadarNotFound):
            radar.tile(tile)

    def test_a_frame_from_before_a_restart_is_looked_up(self):
        radar, lists, _, _ = make_radar()
        self.assertEqual(radar.tile("/tiles/radar/noaa/conus/20270115T100000Z/7/29/48.png"), PNG)
        self.assertEqual(len(lists.urls), 1)

    def test_only_pictures_are_passed_on(self):
        radar, _, tiles, _ = make_radar()
        tiles.kind, tiles.body = "text/xml", b"<ServiceExceptionReport/>"
        with self.assertRaises(r.RadarError):
            radar.tile("/tiles/radar/noaa/conus/20270115T100000Z/7/29/48.png")

    def test_fetches_are_capped_per_minute(self):
        radar, _, tiles, clock = make_radar()
        path = "/tiles/radar/noaa/conus/20270115T100000Z/7/29/48.png"
        with mock.patch.object(r, "TILE_FETCHES_PER_MINUTE", 3):
            for _ in range(3):
                radar.tile(path)
            with self.assertRaises(r.RadarBusy):
                radar.tile(path)
            clock.now += 60
            radar.tile(path)
        self.assertEqual(len(tiles.urls), 4)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(u, "LOCATION_SEARCH", True).start()
        mock.patch.object(u, "LATITUDE", 39.0).start()
        mock.patch.object(u, "LONGITUDE", -98.0).start()
        mock.patch("builtins.print").start()
        self.radar, self.lists, self.tiles, _ = make_radar()
        self.base = self.serve(self.radar)

    def serve(self, radar):
        server = s.make_server(s.Places(limit=5), port=0, radar=radar)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}"

    def get(self, path, base=None):
        try:
            with urllib.request.urlopen((base or self.base) + path, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_home_and_another_place(self):
        status, headers, body = self.get("/api/radar")
        self.assertEqual((status, json.loads(body)["source"]), (200, "noaa"))
        self.assertEqual(headers["Cache-Control"], "no-store")
        status, _, body = self.get("/api/radar?lat=48.9&lon=2.3")
        self.assertEqual((status, json.loads(body)["source"]), (200, "rainviewer"))

    def test_another_place_needs_location_search(self):
        with mock.patch.object(u, "LOCATION_SEARCH", False):
            status, _, body = self.get("/api/radar?lat=48.9&lon=2.3")
            self.assertEqual((status, json.loads(body)["error"]), (403, "location_search_off"))
            self.assertEqual(self.get("/api/radar")[0], 200)
        self.assertEqual(self.get("/api/radar?lat=100&lon=0")[0], 400)

    def test_radar_off(self):
        base = self.serve(None)
        status, _, body = self.get("/api/radar", base)
        self.assertEqual((status, json.loads(body)["error"]), (404, "radar_off"))
        self.assertEqual(self.get("/tiles/radar/noaa/conus/20270115T100000Z/7/29/48.png", base)[0], 404)

    def test_a_service_that_is_down(self):
        self.lists.fail = True
        status, _, body = self.get("/api/radar")
        self.assertEqual((status, json.loads(body)["error"]), (502, "radar_unavailable"))

    def test_tiles_are_kept_for_as_long_as_their_frame_can_be_shown(self):
        tile = json.loads(self.get("/api/radar")[2])["frames"][-1]["tiles"].format(z=7, x=29, y=48)
        status, headers, body = self.get("/" + tile)
        self.assertEqual((status, body, headers["Content-Type"]), (200, PNG, "image/png"))
        self.assertEqual(headers["Cache-Control"], f"public, max-age={r.FRAME_KEEP_SECONDS}")
        status, headers, _ = self.get("/tiles/radar/noaa/conus/20200101T000000Z/7/29/48.png")
        self.assertEqual((status, headers["Cache-Control"]), (404, "no-store"))
        self.tiles.kind = "text/html"
        self.assertEqual(self.get("/" + tile)[0], 502)

    def test_tile_addresses_are_never_printed(self):
        self.tiles.kind = "text/html"
        with mock.patch("builtins.print") as printed:
            self.get("/tiles/radar/noaa/conus/20270115T100000Z/7/29/48.png")
        text = " ".join(str(call) for call in printed.call_args_list)
        self.assertIn("Radar tile", text)
        self.assertNotIn("29", text)
        self.assertNotIn("conus", text)


if __name__ == "__main__":
    unittest.main()
