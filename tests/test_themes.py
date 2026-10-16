import re
import unittest

import helpers
from helpers import ROOT

THEME_DIR = ROOT / "web" / "themes"


def tokens_in(text):
    return set(re.findall(r"(--[a-z-]+)\s*:", text))


class ThemeTests(unittest.TestCase):
    def setUp(self):
        css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
        root_block = re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)
        self.required = tokens_in(root_block) - {"--icon", "--dim"}
        self.themes = sorted(THEME_DIR.glob("*.css"))

    def test_there_are_themes(self):
        self.assertGreaterEqual(len(self.themes), 4)

    def test_theme_names_are_valid(self):
        for path in self.themes:
            with self.subTest(theme=path.name):
                self.assertRegex(path.stem, r"^[a-z0-9-]+$")

    def test_every_theme_defines_every_token(self):
        for path in self.themes:
            with self.subTest(theme=path.name):
                missing = self.required - tokens_in(path.read_text(encoding="utf-8"))
                self.assertEqual(missing, set())

    def test_every_token_is_documented(self):
        docs = (ROOT / "docs" / "themes.md").read_text(encoding="utf-8")
        for token in sorted(self.required):
            with self.subTest(token=token):
                self.assertIn(f"`{token}`", docs)

    def test_the_default_theme_exists_and_is_linked(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        link = re.search(r'id="theme"[^>]*href="themes/([a-z0-9-]+)\.css"', html).group(1)
        self.assertTrue((THEME_DIR / f"{link}.css").exists())
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn(f'DEFAULT_THEME = "{link}"', js)

    def test_themes_are_listed_in_the_docs(self):
        docs = (ROOT / "docs" / "themes.md").read_text(encoding="utf-8")
        for path in self.themes:
            with self.subTest(theme=path.stem):
                self.assertIn(f"`{path.stem}`", docs)


if __name__ == "__main__":
    unittest.main()
