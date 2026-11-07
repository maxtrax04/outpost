import json
import re
import struct
import unittest

import helpers
from helpers import ROOT


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class FrontEndConsistencyTests(unittest.TestCase):
    """The JavaScript and the HTML must agree on element ids (a mismatch fails silently in the browser)."""

    def setUp(self):
        self.html = read("web/index.html")
        self.js = read("web/app.js")
        self.html_ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', self.html))

    def js_ids(self):
        ids = set()
        for path in (ROOT / "web").glob("*.js"):
            text = path.read_text(encoding="utf-8")
            ids |= set(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', text))
            ids |= set(re.findall(r'setText\("([A-Za-z0-9_-]+)"', text))
        return ids

    def test_every_id_used_by_the_script_exists_in_the_page(self):
        for element_id in sorted(self.js_ids()):
            with self.subTest(id=element_id):
                self.assertIn(element_id, self.html_ids)

    def test_scripts_are_loaded_in_the_right_order(self):
        scripts = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(scripts, ["dim.js", "themes.js", "app.js"])

    def test_every_script_file_exists(self):
        for name in re.findall(r'<script src="([^"]+)"', self.html):
            with self.subTest(script=name):
                self.assertTrue((ROOT / "web" / name).exists())

    def test_the_stylesheet_exists(self):
        self.assertTrue((ROOT / "web" / "style.css").exists())

    def test_settings_the_script_reads_are_written_by_the_updater(self):
        updater = read("app/outpost_updater.py")
        for key in ("latitude", "longitude", "theme", "themes", "dim", "ui", "subtitle", "alerts_always_show", "theme_switcher"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', updater)

    def test_data_fields_the_script_reads_exist_in_the_payload(self):
        updater = read("app/outpost_updater.py")
        for key in ("alerts_supported", "generated_at", "update_interval_seconds", "coordinates", "version", "source"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', updater)


def served_file(href):
    """Where a URL path from the page lives in the repository (web/ and assets/ are both served from the site root)."""
    for base in (ROOT / "web", ROOT):
        if (base / href).exists():
            return base / href
    return ROOT / "web" / href


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", data[16:24])


class HomeScreenTests(unittest.TestCase):
    """The web app manifest, its icons, and the head tags that make Add to Home Screen work."""

    def setUp(self):
        self.html = read("web/index.html")
        self.manifest = json.loads(read("web/manifest.webmanifest"))

    def test_the_page_links_the_manifest_and_icons(self):
        self.assertIn('rel="manifest" href="manifest.webmanifest"', self.html)
        self.assertIn('rel="apple-touch-icon"', self.html)
        self.assertIn('rel="icon"', self.html)
        self.assertIn('name="theme-color"', self.html)

    def test_linked_icon_files_exist(self):
        for href in re.findall(r'<link rel="(?:icon|apple-touch-icon)"[^>]*href="([^"]+)"', self.html):
            with self.subTest(href=href):
                self.assertTrue(served_file(href).exists())

    def test_the_viewport_covers_notched_screens(self):
        self.assertIn("viewport-fit=cover", self.html)

    def test_manifest_has_the_required_fields(self):
        for key in ("name", "short_name", "start_url", "display", "icons", "background_color", "theme_color"):
            with self.subTest(key=key):
                self.assertIn(key, self.manifest)
        self.assertEqual(self.manifest["display"], "standalone")

    def test_manifest_icons_exist_and_match_their_declared_size(self):
        sizes = set()
        for icon in self.manifest["icons"]:
            with self.subTest(icon=icon["src"]):
                path = served_file(icon["src"])
                self.assertTrue(path.exists())
                width, height = png_size(path)
                self.assertEqual(icon["sizes"], f"{width}x{height}")
                sizes.add((width, height, icon.get("purpose", "any")))
        self.assertIn((192, 192, "any"), sizes)
        self.assertIn((512, 512, "any"), sizes)
        self.assertIn((512, 512, "maskable"), sizes)

    def test_apple_touch_icon_is_180_pixels(self):
        self.assertEqual(png_size(ROOT / "assets" / "app" / "apple-touch-icon.png"), (180, 180))

    def test_manifest_colors_match_the_default_theme(self):
        css = read("web/themes/retro-crt.css")
        background = re.search(r"--bg:\s*(#[0-9a-fA-F]{6})", css).group(1).lower()
        self.assertEqual(self.manifest["theme_color"].lower(), background)
        self.assertEqual(self.manifest["background_color"].lower(), background)
        self.assertIn(f'content="{background}"', self.html.lower())


class ResponsiveLayoutTests(unittest.TestCase):
    def setUp(self):
        self.css = read("web/style.css")

    def test_has_phone_tablet_landscape_and_portrait_rules(self):
        for needle in ("max-width: 850px", "max-width: 600px", "orientation: portrait", "orientation: landscape"):
            with self.subTest(rule=needle):
                self.assertIn(needle, self.css)

    def test_respects_safe_areas_and_dynamic_viewport_height(self):
        self.assertIn("env(safe-area-inset-top)", self.css)
        self.assertIn("100dvh", self.css)

    def test_touch_targets_are_at_least_44px(self):
        self.assertRegex(self.css, r"\.theme-button \{[^}]*width: 44px;[^}]*height: 44px;")
        self.assertRegex(self.css, r"\.theme-reset \{[^}]*min-height: 44px;|\.theme-option,\s*\.theme-reset \{[^}]*min-height: 44px;")


if __name__ == "__main__":
    unittest.main()
