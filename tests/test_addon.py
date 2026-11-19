"""The Home Assistant add-on: add-on mode (app/outpost_addon.py), homeassistant/, and its publishing."""

import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import ROOT

import outpost_addon as a

ADDON = ROOT / "homeassistant" / "outpost"
HOME_ASSISTANT = {"location_name": "Cinder Flats Ranch", "latitude": 12.3456, "longitude": -45.6789,
                  "time_zone": "Europe/Oslo", "unit_system": {"length": "km", "temperature": "°C"},
                  "version": "2026.10.0"}

sys.path.insert(0, str(ROOT / "scripts"))
import publish_addon  # noqa: E402


def load_config():
    return json.loads((ADDON / "config.json").read_text(encoding="utf-8"))


class OptionTests(unittest.TestCase):
    def test_option_names_become_settings(self):
        self.assertEqual(a.setting_name("map_zoom"), "OUTPOST_MAP_ZOOM")
        self.assertEqual(a.setting_name("timezone"), "TZ")
        for bad in ("Map", "map-zoom", "1map", "", "x" * 50, "map zoom"):
            with self.subTest(option=bad):
                self.assertIsNone(a.setting_name(bad))

    def test_values(self):
        self.assertEqual(a.value_text(True), "true")
        self.assertEqual(a.value_text(False), "false")
        self.assertEqual(a.value_text(9), "9")
        self.assertEqual(a.value_text(0.35), "0.35")
        self.assertEqual(a.value_text(35.0), "35")
        self.assertEqual(a.value_text(" Cinder Flats "), "Cinder Flats")
        for empty in ("", "   ", None, [], {}, float("nan")):
            with self.subTest(value=empty):
                self.assertIsNone(a.value_text(empty))

    def test_empty_options_are_left_to_outpost(self):
        settings = a.settings_from_options({"provider": "auto", "map": True, "map_zoom": 9, "subtitle": "",
                                            "latitude": None, "Bad-Name": "x"})
        self.assertEqual(settings, {"OUTPOST_PROVIDER": "auto", "OUTPOST_MAP": "true", "OUTPOST_MAP_ZOOM": "9"})


class HomeAssistantTests(unittest.TestCase):
    def test_home_time_zone_and_units(self):
        self.assertEqual(a.from_home_assistant(HOME_ASSISTANT), {
            "OUTPOST_LATITUDE": "12.3456", "OUTPOST_LONGITUDE": "-45.6789",
            "OUTPOST_LOCATION_NAME": "Cinder Flats Ranch", "TZ": "Europe/Oslo", "OUTPOST_UNITS": "metric"})
        self.assertEqual(a.from_home_assistant({"unit_system": {"temperature": "°F"}}), {"OUTPOST_UNITS": "imperial"})

    def test_odd_answers_are_left_out(self):
        self.assertEqual(a.from_home_assistant({"latitude": 91, "longitude": 0, "time_zone": "../etc; rm",
                                                "location_name": "  ", "unit_system": "metric"}), {})
        self.assertEqual(a.from_home_assistant({"latitude": True, "longitude": 1.0}), {})
        self.assertEqual(a.from_home_assistant({}), {})

    def test_the_options_win_and_a_location_is_replaced_whole(self):
        ha = a.from_home_assistant(HOME_ASSISTANT)
        settings = a.combine({"OUTPOST_UNITS": "imperial"}, ha)
        self.assertEqual(settings["OUTPOST_UNITS"], "imperial")
        self.assertEqual(settings["OUTPOST_LATITUDE"], "12.3456")
        moved = a.combine({"OUTPOST_LATITUDE": "1.5", "OUTPOST_LONGITUDE": "2.5"}, ha)
        self.assertEqual((moved["OUTPOST_LATITUDE"], moved["OUTPOST_LONGITUDE"]), ("1.5", "2.5"))
        # Home Assistant's home name is not given to another place
        self.assertNotIn("OUTPOST_LOCATION_NAME", moved)
        self.assertEqual(moved["TZ"], "Europe/Oslo")

    def test_the_token_is_sent_to_the_supervisor_only(self):
        asked = []
        config = a.home_assistant_config("secret-token", lambda url, token: asked.append((url, token)) or HOME_ASSISTANT)
        self.assertEqual(config, HOME_ASSISTANT)
        self.assertEqual(asked, [("http://supervisor/core/api/config", "secret-token")])
        self.assertEqual(a.home_assistant_config("", lambda url, token: self.fail("asked without a token")), {})

    def test_home_assistant_unreachable(self):
        def fail(url, token):
            raise OSError("no route")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(a.home_assistant_config("token", fail), {})
        self.assertIn("Could not read Home Assistant", stderr.getvalue())


class RunTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.options = self.folder / "options.json"
        self.env = self.folder / "run" / "addon.env"
        self.snippet = self.folder / "nginx" / "addon.conf"

    def run_addon(self, environ, get=None):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = a.run(self.options, self.env, self.snippet, environ, get or (lambda url, token: HOME_ASSISTANT))
        return result, stderr.getvalue()

    def test_outside_home_assistant_nothing_changes(self):
        result, said = self.run_addon({})
        self.assertFalse(result)
        self.assertFalse(self.env.exists())
        self.assertNotIn("listen", self.snippet.read_text(encoding="utf-8"))
        self.assertEqual(said, "")

    def test_as_an_add_on(self):
        self.options.write_text(json.dumps({"provider": "auto", "map": True, "subtitle": "It's $HOME \"here\""}))
        result, said = self.run_addon({"SUPERVISOR_TOKEN": "secret-token"})
        self.assertTrue(result)
        snippet = self.snippet.read_text(encoding="utf-8")
        self.assertIn(f"listen {a.INGRESS_PORT};", snippet)
        self.assertIn("if ($outpost_ingress_refused)", snippet)
        env = self.env.read_text(encoding="utf-8")
        self.assertIn("export OUTPOST_PROVIDER=auto", env)
        self.assertNotIn("secret-token", env)
        self.assertIn("home location, time zone, units from Home Assistant", said)
        # Coordinates and the token are never printed
        for secret in ("12.3456", "45.6789", "secret-token"):
            self.assertNotIn(secret, said)

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_start_sh_reads_back_exactly_what_was_set(self):
        subtitle = "It's $HOME \"here\" `date` \\ and\nmore"
        self.options.write_text(json.dumps({"subtitle": subtitle, "map_zoom": 9}))
        self.run_addon({"SUPERVISOR_TOKEN": "t"})
        output = subprocess.run(["bash", "-c", f'. "{self.env}"; printf "%s|%s|%s" "$OUTPOST_SUBTITLE" "$OUTPOST_MAP_ZOOM" "$TZ"'],
                                capture_output=True, text=True, check=True).stdout
        self.assertEqual(output, f"{subtitle}|9|Europe/Oslo")

    def test_broken_options_still_start(self):
        self.options.write_text("{not json")
        result, said = self.run_addon({})
        self.assertTrue(result)
        self.assertIn("Could not read the add-on's options", said)
        self.assertEqual(self.env.read_text(encoding="utf-8").count("export"), 0)


class StartupTests(unittest.TestCase):
    def test_start_sh_reads_the_settings_before_anything_starts(self):
        start = (ROOT / "app" / "start.sh").read_text(encoding="utf-8")
        self.assertLess(start.index("python3 /app/outpost_addon.py"), start.index(". /run/outpost/addon.env"))
        self.assertLess(start.index(". /run/outpost/addon.env"), start.index("python3 /app/outpost_web.py"))

    def test_nginx_answers_ingress_only_from_the_supervisor(self):
        conf = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
        self.assertIn('map "$server_port:$remote_addr" $outpost_ingress_refused {', conf)
        self.assertIn(f'"~^{a.INGRESS_PORT}:" 1;', conf)
        self.assertIn(f'"{a.INGRESS_PORT}:{a.INGRESS_PROXY}" 0;', conf)
        self.assertIn("include /etc/nginx/outpost/addon.conf;", conf)
        self.assertIn("python3 /app/outpost_addon.py", (ROOT / "Dockerfile").read_text(encoding="utf-8"))


class AddonFolderTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_the_basics(self):
        for key in ("name", "version", "slug", "description", "arch"):
            self.assertIn(key, self.config)
        # The release workflow sets the version
        self.assertEqual(self.config["version"], "0.0.0")
        self.assertEqual(self.config["image"], "ghcr.io/maxtrax04/outpost")
        self.assertEqual(self.config["ingress_port"], a.INGRESS_PORT)
        self.assertTrue(self.config["ingress"])
        self.assertTrue(self.config["homeassistant_api"])
        # The panel is for every Home Assistant user, not only administrators
        self.assertIs(self.config["panel_admin"], False)
        # The direct port is offered but off
        self.assertEqual(self.config["ports"], {"80/tcp": None})
        for name in ("README.md", "DOCS.md", "icon.png", "logo.png", "translations/en.yaml"):
            self.assertTrue((ADDON / name).is_file(), name)
        self.assertTrue((ADDON.parent / "repository.yaml").is_file())

    def test_built_for_what_the_image_is_built_for(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        platforms = re.search(r"platforms: (linux/\S+)", workflow).group(1).split(",")
        names = {"linux/amd64": "amd64", "linux/arm64": "aarch64"}
        self.assertEqual(sorted(self.config["arch"]), sorted(names[p] for p in platforms))
        self.assertIn("io.hass.type=addon", workflow)
        self.assertIn("io.hass.version=${{ steps.meta.outputs.version }}", workflow)
        self.assertIn("python3 ../scripts/publish_addon.py", workflow)

    def test_every_option_is_a_documented_setting(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for option in self.config["schema"]:
            name = a.setting_name(option)
            with self.subTest(option=option):
                self.assertIsNotNone(name)
                if name != "TZ":
                    # A settings table row (OUTPOST_DIM_START and OUTPOST_DIM_END share one)
                    self.assertRegex(readme, rf"(?m)^\| [^\n]*`{name}` [|/]")
                self.assertIn(f"{name}=", example)
        self.assertLessEqual(set(self.config["options"]), set(self.config["schema"]))

    def test_every_option_has_a_label(self):
        translations = (ADDON / "translations" / "en.yaml").read_text(encoding="utf-8")
        labelled = set(re.findall(r"^  ([a-z_]+):\n    name: ", translations, re.M))
        self.assertEqual(labelled, set(self.config["schema"]))
        for port in self.config["ports"]:
            self.assertIn(f"  {port}: ", translations)

    def test_switches_show_outposts_defaults(self):
        # Home Assistant shows an optional switch with no value as off, so a switch whose setting
        # defaults to on would look off while it is on: every switch is required and has the
        # default from the README's settings table
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        switches = [option for option, kind in self.config["schema"].items() if kind.startswith("bool")]
        self.assertIn("auto_dim", switches)
        for option in switches:
            with self.subTest(option=option):
                self.assertEqual(self.config["schema"][option], "bool")
                name = a.setting_name(option)
                default = re.search(rf"(?m)^\| `{name}` \| `(true|false)` \|", readme).group(1)
                self.assertIs(self.config["options"][option], default == "true")

    def test_list_options_match_what_outpost_accepts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for option in ("provider", "alerts_provider", "units", "effects", "dim_mode"):
            values = re.match(r"list\((.*)\)\??$", self.config["schema"][option]).group(1).split("|")
            name = a.setting_name(option)
            row = next(line for line in readme.splitlines() if line.startswith(f"| `{name}` |"))
            example = (ROOT / ".env.example").read_text(encoding="utf-8")
            block = example[:example.index(f"{name}=")].rsplit("\n\n", 1)[-1]
            for value in values:
                with self.subTest(option=option, value=value):
                    # In the README's row, or in the comment above the setting in .env.example
                    self.assertRegex(row + block, rf"(?<![\w-]){re.escape(value)}(?![\w-])")


class PublishTests(unittest.TestCase):
    def test_publishes_with_the_version_and_replaces_what_was_there(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / ".git").mkdir()
            (target / ".git" / "HEAD").write_text("ref: refs/heads/beta\n")
            (target / "old-file.txt").write_text("gone")
            (target / "outpost").mkdir()
            (target / "outpost" / "stale.md").write_text("gone")
            publish_addon.publish("0.7.0-beta.9", target)
            config = json.loads((target / "outpost" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["version"], "0.7.0-beta.9")
            self.assertEqual({k: v for k, v in config.items() if k != "version"},
                             {k: v for k, v in load_config().items() if k != "version"})
            self.assertTrue((target / "repository.yaml").is_file())
            self.assertTrue((target / "outpost" / "CHANGELOG.md").read_text(encoding="utf-8").startswith("# Changelog"))
            self.assertFalse((target / "old-file.txt").exists())
            self.assertFalse((target / "outpost" / "stale.md").exists())
            self.assertTrue((target / ".git" / "HEAD").exists())

    def test_only_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            for bad in ("v0.7.0", "latest", "0.7", "0.7.0; rm -rf /"):
                with self.subTest(version=bad), self.assertRaises(ValueError):
                    publish_addon.publish(bad, Path(folder))


if __name__ == "__main__":
    unittest.main()
