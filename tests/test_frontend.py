import re
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
        ids = set(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', self.js))
        ids |= set(re.findall(r'setText\("([A-Za-z0-9_-]+)"', self.js))
        return ids

    def test_every_id_used_by_the_script_exists_in_the_page(self):
        for element_id in sorted(self.js_ids()):
            with self.subTest(id=element_id):
                self.assertIn(element_id, self.html_ids)

    def test_scripts_are_loaded_in_the_right_order(self):
        scripts = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(scripts, ["dim.js", "app.js"])

    def test_every_script_file_exists(self):
        for name in re.findall(r'<script src="([^"]+)"', self.html):
            with self.subTest(script=name):
                self.assertTrue((ROOT / "web" / name).exists())

    def test_the_stylesheet_exists(self):
        self.assertTrue((ROOT / "web" / "style.css").exists())

    def test_settings_the_script_reads_are_written_by_the_updater(self):
        updater = read("app/outpost_updater.py")
        for key in ("latitude", "longitude", "theme", "dim", "ui", "subtitle", "alerts_always_show"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', updater)

    def test_data_fields_the_script_reads_exist_in_the_payload(self):
        updater = read("app/outpost_updater.py")
        for key in ("alerts_supported", "generated_at", "update_interval_seconds", "coordinates", "version", "source"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', updater)


if __name__ == "__main__":
    unittest.main()
