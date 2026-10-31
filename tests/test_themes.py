import re
import unittest

import helpers
from helpers import ROOT

THEME_DIR = ROOT / "web" / "themes"


def hex_color(css, token):
    match = re.search(rf"{re.escape(token)}\s*:\s*(#[0-9a-fA-F]{{6}})\b", css)
    return match.group(1) if match else None


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


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

    def test_text_is_readable_on_the_background(self):
        # Minimum contrast ratios: main text 7 (WCAG AAA), colored text 4.5 (AA), dim text 3.5
        minimums = {"--text": 7.0, "--accent": 4.5, "--warn": 4.5, "--danger": 4.5, "--text-dim": 3.5}
        for path in self.themes:
            css = path.read_text(encoding="utf-8")
            background = hex_color(css, "--bg")
            self.assertIsNotNone(background, f"{path.name} needs a #rrggbb --bg for this check")
            for token, minimum in minimums.items():
                color = hex_color(css, token)
                if color is None:
                    continue
                with self.subTest(theme=path.stem, token=token):
                    ratio = contrast(color, background)
                    self.assertGreaterEqual(ratio, minimum, f"{token} {color} on {background} has contrast {ratio:.1f}")

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
