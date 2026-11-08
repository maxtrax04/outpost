import re
import unittest

import helpers
from helpers import ROOT

LOGO_DIR = ROOT / "assets" / "logo"
LOGOS = ("mark", "wordmark", "lockup")


def view_box(svg):
    return [float(n) for n in re.search(r'<svg[^>]*\sviewBox="([^"]+)"', svg).group(1).split()]


class LogoFileTests(unittest.TestCase):
    """The logo is tinted by each theme, so the files must be plain one-color shapes."""

    def test_logo_files_exist(self):
        for name in LOGOS:
            with self.subTest(logo=name):
                self.assertTrue((LOGO_DIR / f"{name}.svg").is_file())

    def test_logos_take_their_color_from_the_theme(self):
        for name in LOGOS:
            svg = (LOGO_DIR / f"{name}.svg").read_text(encoding="utf-8")
            with self.subTest(logo=name):
                self.assertRegex(svg, r'<svg[^>]*\sfill="currentColor"')
                self.assertNotRegex(svg, r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", "a fixed color")
                self.assertNotRegex(svg, r'\s(fill|stroke)="(?!currentColor|none)', "a fixed fill or stroke")

    def test_logos_are_plain_shapes(self):
        # Text must be converted to outlines; no fonts, images, scripts, or styles that the CSP would block
        for name in LOGOS:
            svg = (LOGO_DIR / f"{name}.svg").read_text(encoding="utf-8")
            with self.subTest(logo=name):
                self.assertEqual(len(view_box(svg)), 4)
                for pattern in (r"<text\b", r"<image\b", r"<script\b", r"<style\b", r"<font\b", r"\sstyle=",
                                r"\sclass=", r"href=", r"data:", r"@import"):
                    self.assertNotRegex(svg, pattern)

    def test_the_header_uses_the_wordmark_at_its_own_shape(self):
        css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
        self.assertIn('url("assets/logo/wordmark.svg")', css)
        # If the wordmark is redrawn at a different size, the header box must change with it
        _, _, width, height = view_box((LOGO_DIR / "wordmark.svg").read_text(encoding="utf-8"))
        ratio = re.search(r"\.title-logo\s*\{[^}]*aspect-ratio:\s*([\d.]+)\s*/\s*([\d.]+)", css)
        self.assertAlmostEqual(float(ratio.group(1)) / float(ratio.group(2)), width / height, places=3)

    def test_the_title_text_stays_in_the_page(self):
        # Screen readers read the text even when the logo is shown
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'<h1 class="title">.*<span class="title-text">OUTPOST</span></h1>')
        self.assertRegex(html, r'<span class="title-logo-glow" aria-hidden="true">')


class AppIconTests(unittest.TestCase):
    def test_favicon_is_the_mark(self):
        favicon = (ROOT / "assets" / "app" / "favicon.svg").read_text(encoding="utf-8")
        mark_shapes = re.findall(r'\sd="([^"]+)"', (LOGO_DIR / "mark.svg").read_text(encoding="utf-8"))
        for shape in mark_shapes:
            self.assertIn(shape, favicon, "favicon.svg is out of date; rebuild it from assets/logo/mark.svg")

    def test_app_icons_have_the_right_sizes(self):
        for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512),
                           ("apple-touch-icon.png", 180)):
            data = (ROOT / "assets" / "app" / name).read_bytes()
            with self.subTest(icon=name):
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual((int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")), (size, size))


if __name__ == "__main__":
    unittest.main()
