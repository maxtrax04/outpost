import re
import unittest

import helpers
from helpers import ROOT

import outpost_updater as u
from providers import nws, openmeteo

ICON_DIR = ROOT / "assets" / "icons"


def icons_in_app_js():
    text = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const ICONS = \[(.*?)\];", text, re.S).group(1)
    return re.findall(r'"([a-z-]+)"', block)


class IconTests(unittest.TestCase):
    def setUp(self):
        self.known = set(icons_in_app_js())

    def test_every_listed_icon_has_a_file(self):
        for name in self.known:
            with self.subTest(icon=name):
                self.assertTrue((ICON_DIR / f"{name}.svg").exists())

    def test_every_icon_file_is_listed(self):
        files = {p.stem for p in ICON_DIR.glob("*.svg")}
        self.assertEqual(files, self.known)

    def test_icons_are_themeable(self):
        for path in ICON_DIR.glob("*.svg"):
            with self.subTest(icon=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn('viewBox="0 0 64 64"', text)
                self.assertIn("currentColor", text)

    def test_unknown_fallback_exists(self):
        self.assertIn("unknown", self.known)

    def test_open_meteo_only_uses_known_icons(self):
        used = {icon for _, icon in openmeteo.WMO_CODES.values()} | set(openmeteo.NIGHT_ICONS.values())
        self.assertLessEqual(used, self.known)

    def test_nws_only_uses_known_icons(self):
        samples = ["Sunny", "Clear", "Partly Cloudy", "Cloudy", "Fog", "Drizzle", "Rain", "Sleet", "Snow",
                   "Thunderstorms", "Breezy", "???"]
        used = {nws.icon_from_text(text, day) for text in samples for day in (True, False)}
        self.assertLessEqual(used, self.known)

    def test_mock_provider_only_uses_known_icons(self):
        used = set()
        for _ in range(200):
            payload = u.build_mock_payload()
            used.add(payload["current"]["icon"])
            used.update(day["icon"] for day in payload["forecast"])
        self.assertLessEqual(used, self.known)


if __name__ == "__main__":
    unittest.main()
