import re
import unittest

import helpers
from helpers import ROOT


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class ReleaseConsistencyTests(unittest.TestCase):
    def test_version_file_is_semver(self):
        self.assertRegex(read("VERSION").strip(), r"^\d+\.\d+\.\d+$")

    def test_dockerfile_base_image_is_pinned(self):
        match = re.search(r"^FROM (\S+)", read("Dockerfile"), re.M)
        self.assertIsNotNone(match, "Dockerfile has no FROM line")
        image = match.group(1)
        self.assertRegex(image, r":\d+\.\d+(\.\d+)?(-[a-z0-9.]+)?$", f"{image} should be pinned to a version, not a floating tag")

    def test_changelog_has_an_entry_for_the_current_version(self):
        version = read("VERSION").strip()
        pattern = re.compile(rf"^## \[{re.escape(version)}\]", re.M)
        self.assertRegex(read("CHANGELOG.md"), pattern, "CHANGELOG.md has no entry for this version")

    def test_changelog_has_an_unreleased_section(self):
        self.assertIn("## [Unreleased]", read("CHANGELOG.md"))


class AutomationTests(unittest.TestCase):
    def test_workflows_exist(self):
        for name in ("ci.yml", "release.yml"):
            with self.subTest(workflow=name):
                self.assertTrue((ROOT / ".github" / "workflows" / name).exists())

    def test_dependabot_watches_docker_and_actions(self):
        text = read(".github/dependabot.yml")
        self.assertIn('package-ecosystem: "docker"', text)
        self.assertIn('package-ecosystem: "github-actions"', text)

    def test_release_workflow_publishes_on_version_tags(self):
        text = read(".github/workflows/release.yml")
        self.assertIn('tags: ["v*"]', text)
        self.assertIn("linux/amd64,linux/arm64", text)


class SettingsDocumentationTests(unittest.TestCase):
    """Every OUTPOST_* setting the code or compose file uses must be documented."""

    def setUp(self):
        sources = list((ROOT / "app").rglob("*.py")) + [ROOT / "docker-compose.yml"]
        names = set()
        for path in sources:
            names.update(re.findall(r"OUTPOST_[A-Z][A-Z0-9_]*", path.read_text(encoding="utf-8")))
        self.names = {name.rstrip("_") for name in names}

    def test_settings_were_found(self):
        self.assertIn("OUTPOST_PROVIDER", self.names)

    def test_settings_are_in_env_example(self):
        text = read(".env.example")
        for name in sorted(self.names):
            with self.subTest(setting=name):
                self.assertIn(name, text)

    def test_settings_are_in_the_readme(self):
        text = read("README.md")
        for name in sorted(self.names):
            with self.subTest(setting=name):
                self.assertIn(name, text)


class FontLicenseTests(unittest.TestCase):
    def test_every_bundled_font_has_a_license_file(self):
        folder = ROOT / "assets" / "fonts"
        fonts = [p for p in folder.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2")]
        licenses = [p for p in folder.iterdir() if re.search(r"(ofl|license|licence)", p.name, re.I)]
        for font in fonts:
            with self.subTest(font=font.name):
                self.assertTrue(licenses, f"{font.name} has no license file next to it")
        if fonts:
            self.assertIn("THIRD_PARTY", "".join(p.name for p in ROOT.iterdir()))


class EnvExampleTests(unittest.TestCase):
    def test_keys_are_recognizable(self):
        for line in read(".env.example").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            with self.subTest(line=line):
                key = line.split("=", 1)[0]
                self.assertRegex(key, r"^(OUTPOST_[A-Z0-9_]+|TZ|PIRATEWEATHER_API_KEY|OPENWEATHERMAP_API_KEY)$")


class RepositoryHygieneTests(unittest.TestCase):
    def test_no_personal_files_in_the_tree(self):
        self.assertFalse((ROOT / "data" / "weather.json").exists() and not (ROOT / ".git").exists(),
                         "data/weather.json should not be part of a shared copy of the project")

    def test_start_script_has_unix_line_endings(self):
        self.assertNotIn(b"\r", (ROOT / "app" / "start.sh").read_bytes())


if __name__ == "__main__":
    unittest.main()
