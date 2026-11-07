import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT

import outpost_web as web


def directives(policy):
    return dict(part.strip().split(" ", 1) for part in policy.split(";"))


class FrameAncestorsTests(unittest.TestCase):
    def test_default_is_same_site_only(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(web.parse_frame_ancestors(value), ("'self'", None))

    def test_home_assistant_addresses_are_accepted(self):
        value, warning = web.parse_frame_ancestors("self http://homeassistant.local:8123, https://ha.example.com/")
        self.assertIsNone(warning)
        self.assertEqual(value, "'self' http://homeassistant.local:8123 https://ha.example.com")

    def test_keywords_work_with_or_without_quotes(self):
        self.assertEqual(web.parse_frame_ancestors("none")[0], "'none'")
        self.assertEqual(web.parse_frame_ancestors("'self'")[0], "'self'")
        self.assertEqual(web.parse_frame_ancestors("SELF")[0], "'self'")

    def test_wildcards(self):
        self.assertEqual(web.parse_frame_ancestors("https://*.example.com")[0], "https://*.example.com")
        self.assertEqual(web.parse_frame_ancestors("*")[0], "*")

    def test_duplicates_are_dropped(self):
        self.assertEqual(web.parse_frame_ancestors("self self")[0], "'self'")

    def test_anything_that_could_break_the_header_is_rejected(self):
        bad = (
            "http://ha.local; script-src *", 'http://ha.local" always', "http://ha.local\nadd_header X 1",
            "javascript:alert(1)", "ftp://ha.local", "http://", "ha.local:8123/path", "'unsafe-inline'",
            "http://ha.local:999999",
        )
        for value in bad:
            with self.subTest(value=value):
                result, warning = web.parse_frame_ancestors(value)
                self.assertEqual(result, "'self'")
                self.assertIn("Invalid OUTPOST_FRAME_ANCESTORS", warning)

    def test_none_cannot_be_combined(self):
        result, warning = web.parse_frame_ancestors("none http://ha.local")
        self.assertEqual(result, "'self'")
        self.assertIn("cannot combine none", warning)


class PolicyTests(unittest.TestCase):
    def test_everything_is_limited_to_outpost_itself(self):
        policy = directives(web.content_security_policy())
        self.assertEqual(policy["default-src"], "'none'")
        for name in ("script-src", "style-src", "img-src", "font-src", "connect-src", "manifest-src"):
            with self.subTest(directive=name):
                self.assertEqual(policy[name], "'self'")
        self.assertEqual(policy["frame-ancestors"], "'self'")
        self.assertEqual(policy["base-uri"], "'none'")

    def test_no_unsafe_sources(self):
        policy = web.content_security_policy()
        for unsafe in ("unsafe-inline", "unsafe-eval", "data:", "http:", "https:"):
            with self.subTest(source=unsafe):
                self.assertNotIn(unsafe, policy)

    def test_frame_ancestors_setting_is_used(self):
        policy = directives(web.content_security_policy("'self' http://homeassistant.local:8123"))
        self.assertEqual(policy["frame-ancestors"], "'self' http://homeassistant.local:8123")

    def test_snippet_has_every_header(self):
        snippet = web.nginx_snippet()
        for header in ("Content-Security-Policy", "X-Content-Type-Options \"nosniff\"", "Referrer-Policy \"no-referrer\""):
            with self.subTest(header=header):
                self.assertRegex(snippet, rf"add_header {header}.* always;")

    def test_writing_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "security-headers.conf"
            with mock.patch("builtins.print") as printed:
                used = web.write_headers(path, "http://ha.local:8123")
                self.assertEqual(used, "http://ha.local:8123")
                self.assertIn("frame-ancestors http://ha.local:8123", path.read_text())
                web.write_headers(path, "bad value;")
            self.assertIn("frame-ancestors 'self'", path.read_text())
            self.assertIn("Invalid", str(printed.call_args_list[-1]))
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


class FrontEndFitsThePolicyTests(unittest.TestCase):
    """The policy has no unsafe-inline, so the page must not rely on inline code or styles."""

    def test_no_inline_scripts_styles_or_handlers(self):
        for path in sorted((ROOT / "web").glob("*.html")):
            html = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>", "inline <script>")
                self.assertNotRegex(html, r"<style\b", "inline <style>")
                self.assertNotRegex(html, r"\sstyle=", "style attribute")
                self.assertNotRegex(html, r"\son[a-z]+=", "inline event handler")
                self.assertNotRegex(html, r"""(?:src|href)=["']https?://""", "file from another site")

    def test_scripts_do_not_need_eval_or_inline_styles(self):
        for path in sorted((ROOT / "web").glob("*.js")):
            code = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(code, r"\beval\(|new Function\(|setAttribute\(\s*[\"']style[\"']|\.innerHTML\s*=")

    def test_built_in_and_example_themes_load_nothing_from_other_sites(self):
        sheets = [ROOT / "web" / "style.css"] + sorted((ROOT / "web" / "themes").glob("*/theme.css")) \
            + sorted((ROOT / "examples" / "themes").glob("*/theme.css"))
        for path in sheets:
            css = path.read_text(encoding="utf-8")
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertNotRegex(css, r"""url\(\s*["']?(?:https?:|//|data:)""")
                self.assertNotIn("@import", css)


class NginxIncludesTheHeadersTests(unittest.TestCase):
    def test_every_block_that_sets_headers_includes_them(self):
        conf = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
        include = "include /etc/nginx/outpost/security-headers.conf;"
        server_level = re.split(r"^\s*location\b", conf, maxsplit=1, flags=re.M)[0]
        self.assertIn(include, server_level)
        for block in re.findall(r"location[^{]*\{([^}]*)\}", conf):
            if "add_header" in block:
                with self.subTest(block=block.strip()[:40]):
                    self.assertIn(include, block)

    def test_headers_are_written_at_build_and_at_startup(self):
        self.assertIn("RUN python3 /app/outpost_web.py && nginx -t", (ROOT / "Dockerfile").read_text(encoding="utf-8"))
        start = (ROOT / "app" / "start.sh").read_text(encoding="utf-8")
        self.assertLess(start.index("outpost_web.py"), start.index("exec nginx"))


if __name__ == "__main__":
    unittest.main()
