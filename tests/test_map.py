"""The map's settings and its nginx tile cache (app/outpost_map.py, docs/map-design.md)."""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT

import outpost_map as m
import outpost_updater as u

UA = "Outpost/1.0 (maps@example.org; +https://github.com/maxtrax04/outpost)"


def on(**env):
    return m.settings({"OUTPOST_MAP": "true", **env}, contact="maps@example.org")


class SettingTests(unittest.TestCase):
    def test_off_by_default(self):
        settings = m.settings({}, contact="maps@example.org")
        self.assertEqual((settings["enabled"], settings["zoom"], settings["problems"]), (False, 7, []))
        self.assertEqual(settings["tiles"]["template"], m.DEFAULT_TILES)

    def test_openstreetmap_needs_a_contact(self):
        settings = m.settings({"OUTPOST_MAP": "true"}, contact="")
        self.assertFalse(settings["enabled"])
        self.assertIn("OUTPOST_CONTACT", settings["problems"][0])
        self.assertTrue(on()["enabled"])
        # Another tile server decides for itself
        other = m.settings({"OUTPOST_MAP": "true", "OUTPOST_MAP_TILES": "http://tiles.lan:8080/shortbread/{z}/{x}/{y}.pbf"}, contact="")
        self.assertTrue(other["enabled"])

    def test_zoom(self):
        for value, expected, warned in (("4", 4, False), (" 12 ", 12, False), ("3", 7, True), ("13", 7, True),
                                        ("7.5", 7, True), ("", 7, False)):
            with self.subTest(value=value):
                zoom, warning = m.zoom_setting(value)
                self.assertEqual((zoom, warning is not None), (expected, warned))

    def test_tile_addresses(self):
        parts, warning = m.tiles_setting("https://tiles.example.org:8443/a/b-c/{z}/{x}/{y}.mvt")
        self.assertIsNone(warning)
        self.assertEqual((parts["scheme"], parts["host"], parts["port"], parts["prefix"], parts["suffix"]),
                         ("https", "tiles.example.org", "8443", "/a/b-c/", ".mvt"))
        for bad in ("ftp://x.org/{z}/{x}/{y}", "https://x.org/{x}/{y}/{z}", "https://x.org/$host/{z}/{x}/{y}",
                    "https://x.org/a b/{z}/{x}/{y}", "https://x.org/{z}/{x}/{y}.mvt;", "https://x.org:99999/{z}/{x}/{y}",
                    'https://x.org/"/{z}/{x}/{y}', "https://-x.org/{z}/{x}/{y}"):
            with self.subTest(bad=bad):
                parts, warning = m.tiles_setting(bad)
                self.assertIsNotNone(warning)
                self.assertEqual(parts["template"], m.DEFAULT_TILES)

    def test_config_for_the_dashboard(self):
        self.assertEqual(m.config(on(OUTPOST_MAP_ZOOM="9")), {
            "enabled": True, "zoom": 9, "attribution": "© OpenStreetMap",
            "attribution_url": "https://www.openstreetmap.org/copyright"})

    def test_config_json_has_the_map(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(u, "DATA_PATH", Path(folder) / "weather.json"), \
                mock.patch.dict("os.environ", {"OUTPOST_MAP": "true"}), \
                mock.patch.object(u, "CONTACT", "maps@example.org"), mock.patch("builtins.print"):
            u.write_config()
            config = json.loads((Path(folder) / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["map"]["enabled"], True)
        self.assertEqual(config["map"]["zoom"], 7)

    def test_every_setting_is_documented(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in ("OUTPOST_MAP", "OUTPOST_MAP_ZOOM", "OUTPOST_MAP_TILES"):
            self.assertIn(f"{name}=", example)
            self.assertIn(f"| `{name}` |", readme)


class SnippetTests(unittest.TestCase):
    def test_off_fetches_nothing(self):
        text = m.nginx_snippet(m.settings({}), UA, ["10.0.0.2"])
        self.assertNotIn("location", text)
        self.assertNotIn("proxy_pass", text)

    def test_on(self):
        text = m.nginx_snippet(on(OUTPOST_MAP_ZOOM="8"), UA, ["10.0.0.2", "[fd00::1]"])
        self.assertIn("resolver 10.0.0.2 [fd00::1] ipv6=off valid=300s;", text)
        # Only the zoom the dashboard draws
        self.assertIn('location ~ "^/tiles/base/8/(?<outpost_tile_x>[0-9]{1,4})/(?<outpost_tile_y>[0-9]{1,4})\\.mvt$"', text)
        self.assertIn('set $outpost_tile_server "vector.openstreetmap.org";', text)
        self.assertIn("proxy_pass https://$outpost_tile_server/shortbread_v1/8/$outpost_tile_x/$outpost_tile_y.mvt;", text)
        self.assertIn(f'proxy_set_header User-Agent "{UA}";', text)
        for line in ("access_log off;", "proxy_cache outpost_tile_cache;", "proxy_cache_revalidate on;",
                     "proxy_cache_valid 200 7d;", "proxy_ssl_verify on;", "proxy_ssl_server_name on;",
                     "proxy_ssl_name vector.openstreetmap.org;", 'proxy_set_header Cookie "";',
                     "limit_req zone=outpost_tile_rate burst=40 nodelay;",
                     "include /etc/nginx/outpost/security-headers.conf;"):
            self.assertIn(line, text)
        # The tile policy: honor the server's headers, never ignore them
        self.assertNotIn("proxy_ignore_headers Cache-Control", text)
        self.assertNotIn("Expires", text.replace("Cache-Control and Expires win", ""))

    def test_a_port_and_another_suffix(self):
        settings = m.settings({"OUTPOST_MAP": "true", "OUTPOST_MAP_TILES": "http://tiles.lan:8080/sb/{z}/{x}/{y}.pbf"})
        text = m.nginx_snippet(settings, UA, [])
        self.assertIn(f"resolver {m.FALLBACK_RESOLVER} ipv6=off", text)
        self.assertIn('set $outpost_tile_server "tiles.lan:8080";', text)
        self.assertIn("proxy_pass http://$outpost_tile_server/sb/7/$outpost_tile_x/$outpost_tile_y.pbf;", text)
        self.assertIn('proxy_set_header Host "tiles.lan:8080";', text)

    def test_the_user_agent_cannot_break_out_of_its_string(self):
        text = m.nginx_snippet(on(), 'Evil "agent" $host \\ x', [])
        line = next(line for line in text.splitlines() if "User-Agent" in line)
        self.assertEqual(line, '    proxy_set_header User-Agent "Evil agent host  x";')
        self.assertEqual(m.nginx_text("a; b (c)"), "a; b (c)")

    def test_name_servers(self):
        text = "# comment\nnameserver 127.0.0.11\nnameserver fe80::1%eth0\nnameserver bogus\nsearch lan\n"
        self.assertEqual(m.resolvers(text), ["127.0.0.11", "[fe80::1]"])
        self.assertEqual(m.resolvers(""), [])

    def test_written_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nginx" / "map.conf"
            resolv = Path(folder) / "resolv.conf"
            resolv.write_text("nameserver 10.1.2.3\n", encoding="utf-8")
            m.write_snippet(on(), UA, path, resolv)
            self.assertIn("resolver 10.1.2.3 ", path.read_text(encoding="utf-8"))
            self.assertEqual([item.name for item in path.parent.iterdir()], ["map.conf"])

    def test_nginx_includes_it_and_answers_404_otherwise(self):
        conf = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
        self.assertIn("include /etc/nginx/outpost/map.conf;", conf)
        self.assertIn("keys_zone=outpost_tile_cache:", conf)
        self.assertIn("zone=outpost_tile_rate:", conf)
        block = conf[conf.index("location /tiles/ {"):]
        self.assertIn("return 404;", block[:block.index("}")])

    def test_startup_writes_it(self):
        web = (ROOT / "app" / "outpost_web.py").read_text(encoding="utf-8")
        self.assertIn("outpost_map.write_snippet(", web)
        self.assertIn("python3 /app/outpost_web.py", (ROOT / "app" / "start.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
