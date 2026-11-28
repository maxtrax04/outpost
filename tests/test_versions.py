"""Calendar versions (#118): the VERSION form, and which pre-releases a stable release turns into drafts."""

import re
import shutil
import subprocess
import unittest

import helpers  # noqa: F401
from helpers import ROOT

CALENDAR = re.compile(r"^(20\d\d)\.([1-9]|1[0-2])\.(0|[1-9]\d*)(-(beta|rc)\.[1-9]\d*)?$")


class VersionFormTests(unittest.TestCase):
    def test_version_is_a_calendar_version(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, CALENDAR, "YEAR.MONTH.FIX without leading zeros, optionally -beta.N or -rc.N")

    def test_the_form(self):
        for good in ("2026.12.0", "2027.3.1", "2027.3.0-beta.2", "2026.12.0-rc.1"):
            self.assertRegex(good, CALENDAR)
        for bad in ("2027.03.0", "0.9.0", "2027.13.0", "2027.3", "2027.3.0-alpha.1", "2027.3.01"):
            self.assertNotRegex(bad, CALENDAR)

    def test_the_changelog_has_no_beta_sections_beside_a_release_candidate(self):
        # A release candidate's section replaces its cycle's beta sections
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if "-rc." not in version:
            self.skipTest("not a release candidate")
        cycle = version.split("-")[0]
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertNotIn(f"## [{cycle}-beta.", text)
        self.assertNotRegex(text, r"## \[0\.9\.0")


@unittest.skipIf(shutil.which("bash") is None, "needs bash")
class DraftTests(unittest.TestCase):
    TAGS = ["v0.8.0-beta.1", "v0.9.0-beta.1", "v0.9.0-beta.6", "v2026.12.0-rc.1", "v2026.12.0-rc.2",
            "v2026.12.1-beta.1", "v2027.1.0-beta.1", "v2027.10.0-beta.1", "v2026.9.0-beta.1", "v2026.12.0"]

    def drafts(self, released):
        result = subprocess.run(["bash", str(ROOT / "scripts" / "draft_prereleases.sh"), "--list", released],
                                input="\n".join(self.TAGS) + "\n", capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.split()

    def test_the_first_stable_release_drafts_the_0x_betas_and_its_candidates(self):
        self.assertEqual(self.drafts("2026.12.0"), ["v0.8.0-beta.1", "v0.9.0-beta.1", "v0.9.0-beta.6",
                                                    "v2026.12.0-rc.1", "v2026.12.0-rc.2", "v2026.9.0-beta.1"])

    def test_later_pre_releases_stay(self):
        drafted = self.drafts("2026.12.1")
        self.assertIn("v2026.12.1-beta.1", drafted)
        self.assertNotIn("v2027.1.0-beta.1", drafted)
        # By number, not as text: 2027.10 comes after 2027.1
        self.assertIn("v2027.1.0-beta.1", self.drafts("2027.2.0"))
        self.assertNotIn("v2027.10.0-beta.1", self.drafts("2027.2.0"))
        self.assertNotIn("v2026.12.0", drafted)

    def test_the_workflow_runs_it_for_stable_releases_only(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn('bash scripts/draft_prereleases.sh "${GITHUB_REF_NAME#v}"', workflow)
        self.assertIn("if: ${{ !contains(github.ref_name, '-') }}", workflow)


if __name__ == "__main__":
    unittest.main()
