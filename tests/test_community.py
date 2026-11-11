import io
import tarfile
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (sets up the path to app/)

import outpost_community as c

TOP = "outpost-themes-main"


def archive(files, links=()):
    """A .tar.gz like GitHub's repository archive: {path inside the repository: bytes}."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(f"{TOP}/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for path, target in links:
            info = tarfile.TarInfo(f"{TOP}/{path}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
    return buffer.getvalue()


REPOSITORY = {
    "README.md": b"# Community themes",
    "maxtrax04/weather-desk/theme.css": b"/* Weather Desk: local news */",
    "maxtrax04/weather-desk/wordmark-white.svg": b"<svg/>",
    "maxtrax04/weather-desk/README.md": b"not served",
    "maxtrax04/weather-desk/notes.txt": b"not served",
    "maxtrax04/weather-desk/.hidden.css": b"not served",
    "maxtrax04/weather-desk/fonts/Mono.woff2": b"font",
    "maxtrax04/wristcomp/theme.css": b"/* Wristcomp: field computer */",
    "someone/other/theme.css": b"/* Other: not asked for */",
    "someone/no-css/image.png": b"png",
}


class SettingTests(unittest.TestCase):
    def test_theme_list(self):
        ids, problems = c.wanted_themes(" maxtrax04/weather-desk, MAXTRAX04/Wristcomp maxtrax04/weather-desk ,,")
        self.assertEqual(ids, ["maxtrax04/weather-desk", "maxtrax04/wristcomp"])
        self.assertEqual(problems, [])

    def test_unusable_entries_are_reported(self):
        for bad in ("weather-desk", "a/b/c", "../etc", "a/../b", "user/the_theme", "/a"):
            with self.subTest(entry=bad):
                ids, problems = c.wanted_themes(bad)
                self.assertEqual(ids, [])
                self.assertEqual(len(problems), 1)
                self.assertIn("<username>/<theme>", problems[0])

    def test_empty_means_none(self):
        self.assertEqual(c.wanted_themes(""), ([], []))

    def test_too_many_themes(self):
        ids, problems = c.wanted_themes(",".join(f"user/theme-{n}" for n in range(c.MAX_THEMES + 5)))
        self.assertEqual(len(ids), c.MAX_THEMES)
        self.assertEqual(len(problems), 1)

    def test_ref(self):
        self.assertEqual(c.ref_setting(""), "main")
        for good in ("main", "v1.2.0", "feature/new-themes", "3f2a9c1"):
            self.assertEqual(c.ref_setting(good), good)
        for bad in ("../main", "/main", "main branch", "a" * 101, "main?x=1"):
            self.assertIsNone(c.ref_setting(bad), bad)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name)

    def files(self):
        return sorted(str(p.relative_to(self.out)).replace("\\", "/") for p in self.out.rglob("*") if p.is_file())

    def test_only_the_wanted_themes_and_theme_files_are_kept(self):
        found = c.extract(archive(REPOSITORY), {"maxtrax04/weather-desk", "someone/no-css"}, self.out)
        self.assertEqual(found, {"maxtrax04/weather-desk"})
        self.assertEqual(self.files(), [
            "maxtrax04/weather-desk/fonts/Mono.woff2",
            "maxtrax04/weather-desk/theme.css",
            "maxtrax04/weather-desk/wordmark-white.svg",
            "someone/no-css/image.png",
        ])

    def test_links_and_odd_paths_are_skipped(self):
        data = archive({
            "maxtrax04/evil/theme.css": b"ok",
            "maxtrax04/evil/../../escape.css": b"no",
            "maxtrax04/evil/sub/../up.css": b"no",
        }, links=[("maxtrax04/evil/link.css", "/etc/passwd")])
        c.extract(data, {"maxtrax04/evil"}, self.out)
        self.assertEqual(self.files(), ["maxtrax04/evil/theme.css"])

    def test_large_files_are_skipped(self):
        data = archive({"maxtrax04/big/theme.css": b"ok", "maxtrax04/big/huge.png": b"x" * (c.MAX_FILE_BYTES + 1)})
        c.extract(data, {"maxtrax04/big"}, self.out)
        self.assertEqual(self.files(), ["maxtrax04/big/theme.css"])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "community" / "themes"
        self.print = mock.patch("builtins.print").start()
        self.addCleanup(mock.patch.stopall)
        self.requests = []

    def printed(self):
        return "\n".join(str(call.args[0]) for call in self.print.call_args_list)

    def fetch_from(self, files):
        def fetch(url, user_agent):
            self.requests.append((url, user_agent))
            return archive(files)
        return fetch

    @staticmethod
    def offline(url, user_agent):
        raise urllib.error.URLError("no network")

    def run_update(self, themes, fetch, ref=""):
        env = {"OUTPOST_COMMUNITY_THEMES": themes, "OUTPOST_COMMUNITY_THEMES_REF": ref}
        return c.update(env, root=self.root, fetch=fetch)

    def installed(self):
        return c.installed_themes(self.root)

    def test_nothing_is_downloaded_without_the_setting(self):
        self.assertEqual(self.run_update("", self.fetch_from(REPOSITORY)), 0)
        self.assertEqual(self.requests, [])

    def test_listed_themes_are_downloaded(self):
        self.assertEqual(self.run_update("maxtrax04/weather-desk,maxtrax04/wristcomp", self.fetch_from(REPOSITORY)), 0)
        self.assertEqual(self.installed(), ["maxtrax04/weather-desk", "maxtrax04/wristcomp"])
        self.assertEqual((self.root / "maxtrax04/wristcomp/theme.css").read_bytes(), b"/* Wristcomp: field computer */")
        # One request, for the archive of main, with a User-Agent that has only the version
        self.assertEqual(self.requests, [(f"https://codeload.github.com/{c.REPOSITORY}/tar.gz/main", f"Outpost/{c.read_version()}")])
        self.assertIn("Community themes", self.printed())
        # Nothing left over from the download
        self.assertEqual([p.name for p in self.root.parent.iterdir()], ["themes"])

    def test_a_ref_can_be_chosen(self):
        self.run_update("maxtrax04/wristcomp", self.fetch_from(REPOSITORY), ref="v1.0.0")
        self.assertTrue(self.requests[0][0].endswith("/tar.gz/v1.0.0"))

    def test_a_new_download_replaces_the_old_copy(self):
        self.run_update("maxtrax04/weather-desk", self.fetch_from(REPOSITORY))
        changed = {"maxtrax04/weather-desk/theme.css": b"/* Weather Desk: version two */"}
        self.run_update("maxtrax04/weather-desk", self.fetch_from(changed))
        self.assertEqual((self.root / "maxtrax04/weather-desk/theme.css").read_bytes(), b"/* Weather Desk: version two */")
        # A file the new version no longer has is gone
        self.assertFalse((self.root / "maxtrax04/weather-desk/wordmark-white.svg").exists())

    def test_themes_no_longer_listed_are_removed(self):
        self.run_update("maxtrax04/weather-desk,maxtrax04/wristcomp", self.fetch_from(REPOSITORY))
        self.run_update("maxtrax04/wristcomp", self.fetch_from(REPOSITORY))
        self.assertEqual(self.installed(), ["maxtrax04/wristcomp"])
        self.run_update("", self.fetch_from(REPOSITORY))
        self.assertEqual(self.installed(), [])
        self.assertIn("no longer listed", self.printed())

    def test_without_internet_the_copies_from_before_are_kept(self):
        self.run_update("maxtrax04/weather-desk", self.fetch_from(REPOSITORY))
        self.print.reset_mock()
        self.assertEqual(self.run_update("maxtrax04/weather-desk,maxtrax04/wristcomp", self.offline), 1)
        self.assertEqual(self.installed(), ["maxtrax04/weather-desk"])
        printed = self.printed()
        self.assertIn("Could not download community themes (no network)", printed)
        self.assertIn("using the copies from before: maxtrax04/weather-desk", printed)
        self.assertEqual(self.print.call_count, 1)  # one warning, not one per theme

    def test_without_internet_and_nothing_downloaded_yet(self):
        self.assertEqual(self.run_update("maxtrax04/weather-desk", self.offline), 1)
        self.assertIn("not available until a download works", self.printed())

    def test_a_broken_download_changes_nothing(self):
        self.run_update("maxtrax04/weather-desk", self.fetch_from(REPOSITORY))
        self.assertEqual(self.run_update("maxtrax04/weather-desk", lambda url, ua: b"not a tar file"), 1)
        self.assertEqual(self.installed(), ["maxtrax04/weather-desk"])

    def test_themes_not_in_the_repository_are_reported(self):
        self.run_update("maxtrax04/weather-desk,nobody/missing,someone/no-css", self.fetch_from(REPOSITORY))
        self.assertEqual(self.installed(), ["maxtrax04/weather-desk"])
        self.assertIn("Not found in maxtrax04/outpost-themes (main): nobody/missing, someone/no-css", self.printed())

    def test_an_invalid_ref_falls_back_to_main(self):
        self.run_update("maxtrax04/wristcomp", self.fetch_from(REPOSITORY), ref="../evil")
        self.assertTrue(self.requests[0][0].endswith("/tar.gz/main"))
        self.assertIn("Invalid OUTPOST_COMMUNITY_THEMES_REF", self.printed())

    def test_leftovers_from_an_interrupted_download_are_cleaned_up(self):
        (self.root.parent / ".download-old" / "x").mkdir(parents=True)
        (self.root / "stray.txt").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "stray.txt").write_text("x")
        self.run_update("", self.fetch_from(REPOSITORY))
        self.assertEqual(sorted(p.name for p in self.root.parent.iterdir()), ["themes"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_themes_a_listed_theme_builds_on_are_downloaded_and_kept(self):
        files = dict(REPOSITORY)
        files["maxtrax04/weather-desk-live/theme.css"] = (
            b'/* Weather Desk Live: no boxes */\n@import url("../weather-desk/theme.css");\n'
            b'@import url("../../atomic-broadcast/theme.css");')
        self.run_update("maxtrax04/weather-desk-live", self.fetch_from(files))
        # The sibling it builds on comes too; a built-in theme (../../) is not downloaded
        self.assertEqual(self.installed(), ["maxtrax04/weather-desk", "maxtrax04/weather-desk-live"])
        self.assertIn("because a listed theme builds on it: maxtrax04/weather-desk", self.printed())
        # Offline later: both copies stay
        self.run_update("maxtrax04/weather-desk-live", self.offline)
        self.assertEqual(self.installed(), ["maxtrax04/weather-desk", "maxtrax04/weather-desk-live"])
        # Taken off the list: both go
        self.run_update("", self.offline)
        self.assertEqual(self.installed(), [])

    def test_a_missing_dependency_is_reported_once(self):
        files = {"maxtrax04/a/theme.css": b'@import url("../b/theme.css");',
                 "maxtrax04/c/theme.css": b'@import url("../a/theme.css"); @import url("../d/theme.css");'}
        self.run_update("maxtrax04/c", self.fetch_from(files))
        self.assertEqual(self.installed(), ["maxtrax04/a", "maxtrax04/c"])
        self.assertIn("builds on themes not found in maxtrax04/outpost-themes (main): maxtrax04/b, maxtrax04/d", self.printed())

    def test_dependencies_are_found_in_the_css(self):
        css = ('@import url("../base/theme.css"); .x { background: url(../base/img.svg), url("../../field-station/dial.svg"), '
               'url("own.svg"), url("sub/../x.svg"); }')
        self.assertEqual(c.dependencies("me/theme", css), {"me/base"})
        self.assertEqual(c.dependencies("me/base", '@import url("../base/theme.css");'), set())

    def test_main_never_raises(self):
        with mock.patch.object(c, "update", side_effect=RuntimeError("boom")):
            self.assertEqual(c.main(), 1)
        self.assertIn("Community themes were not updated: boom", self.printed())


if __name__ == "__main__":
    unittest.main()
