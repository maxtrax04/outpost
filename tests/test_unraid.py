"""The unRAID Community Apps template (unraid/outpost.xml, #36), and empty settings (app/outpost_env.py)."""

import json
import os
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ElementTree

import helpers
from helpers import ROOT

import outpost_env

sys.path.insert(0, str(ROOT / "scripts"))
import build_unraid_template as build  # noqa: E402

TEMPLATE = ROOT / "unraid" / "outpost.xml"


def configs():
    root = ElementTree.parse(TEMPLATE).getroot()
    return root, {config.get("Target"): config for config in root.findall("Config")}


class TemplateTests(unittest.TestCase):
    def test_it_is_up_to_date(self):
        self.assertEqual(TEMPLATE.read_text(encoding="utf-8"), build.build(),
                         "run python3 scripts/build_unraid_template.py")

    def test_every_setting_is_in_it(self):
        _, found = configs()
        documented = {name for name, _, _ in build.settings()}
        self.assertIn("OUTPOST_DIM_END", documented)
        self.assertEqual({name for name in found if name.startswith("OUTPOST_")}, documented - build.LEFT_OUT)
        # Everything in .env.example that isn't planned is in the README's table
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        planned = set()
        for block in example.split("\n\n"):
            if "[planned]" in block:
                planned |= set(re.findall(r"(OUTPOST_[A-Z0-9_]+)=", block))
        named = set(re.findall(r"(?m)^#? ?(OUTPOST_[A-Z0-9_]+)=", example))
        self.assertEqual(named - planned, documented)

    def test_defaults_match_the_readme(self):
        _, found = configs()
        for name, default, _ in build.settings():
            if name in build.LEFT_OUT:
                continue
            with self.subTest(name=name):
                config = found[name]
                self.assertEqual(config.text or "", build.TEMPLATE_DEFAULTS.get(name, default))
                self.assertEqual(config.get("Default").split("|")[0], config.text or "")

    def test_secrets_are_masked(self):
        _, found = configs()
        masked = {name for name, config in found.items() if config.get("Mask") == "true"}
        self.assertEqual(masked, {"OUTPOST_PIRATEWEATHER_API_KEY", "OUTPOST_OPENWEATHERMAP_API_KEY",
                                  "OUTPOST_HA_TOKEN", "OUTPOST_MQTT_PASSWORD"})
        for name in masked:
            self.assertEqual(found[name].text or "", "", name)

    def test_choices_are_what_outpost_accepts(self):
        import outpost_updater as u
        _, found = configs()
        accepted = {
            "OUTPOST_ALERTS_PROVIDER": u.ALERTS_PROVIDER_VALUES,
            "OUTPOST_OPENWEATHERMAP_PLAN": u.OPENWEATHERMAP_PLAN_VALUES,
            "OUTPOST_EFFECTS": u.EFFECTS_VALUES,
            "OUTPOST_CLOCK": u.CLOCK_VALUES,
            "OUTPOST_AIR_QUALITY_INDEX": u.AIR_QUALITY_INDEX_VALUES,
        }
        for name, values in accepted.items():
            with self.subTest(name=name):
                self.assertEqual(set(found[name].get("Default").split("|")), set(values))
        providers = set(found["OUTPOST_PROVIDER"].get("Default").split("|"))
        self.assertEqual(providers, set(u.CAPABILITIES) | {"auto"})

    def test_ports_paths_and_links(self):
        root, found = configs()
        self.assertEqual((found["80"].get("Type"), found["80"].text), ("Port", "8088"))
        self.assertEqual((found["/data"].get("Type"), found["/data"].get("Mode")), ("Path", "rw"))
        self.assertEqual(found["/config/themes"].get("Mode"), "ro")
        self.assertEqual(root.findtext("Repository"), "ghcr.io/maxtrax04/outpost:latest")
        self.assertEqual(root.findtext("WebUI"), "http://[IP]:[PORT:80]/")
        for tag, path in (("Icon", "assets/app/icon-512.png"), ("TemplateURL", "unraid/outpost.xml")):
            with self.subTest(tag=tag):
                self.assertEqual(root.findtext(tag), f"{build.RAW}/{path}")
                self.assertTrue((ROOT / path).exists())
        # unRAID passes TZ itself
        self.assertNotIn("TZ", found)

    def test_descriptions_are_plain_text(self):
        _, found = configs()
        for name, config in found.items():
            with self.subTest(name=name):
                self.assertTrue(config.get("Description"))
                self.assertNotRegex(config.get("Description"), r"`|\]\(|\*\*")


class EmptySettingTests(unittest.TestCase):
    """unRAID passes every template variable, empty or not: an empty one means its default."""

    def test_empty_settings_are_dropped(self):
        environ = {"OUTPOST_A": "", "OUTPOST_B": "  ", "OUTPOST_C": "x", "TZ": "", "PATH": "/bin"}
        self.assertEqual(outpost_env.forget_empty_settings(environ), ["OUTPOST_A", "OUTPOST_B"])
        self.assertEqual(environ, {"OUTPOST_C": "x", "TZ": "", "PATH": "/bin"})

    def test_every_script_starts_with_it(self):
        for path in sorted((ROOT / "app").glob("outpost_*.py")):
            text = path.read_text(encoding="utf-8")
            if path.name in ("outpost_env.py", "outpost_addon.py") or not re.search(r"os\.(getenv|environ)", text):
                continue
            with self.subTest(script=path.name):
                self.assertIn("\nimport outpost_env", text)
                # Before anything reads a setting, or imports a module that does
                start = text.index("\nimport outpost_env")
                later = [match.start() for match in
                         re.finditer(r"os\.(getenv|environ)|^(import outpost_(?!env)|from providers)", text, re.M)]
                self.assertLess(start, min(later))

    def test_empty_settings_give_the_defaults(self):
        # Every module's settings, with every documented setting unset and then empty
        code = (
            "import importlib, json, sys\n"
            f"sys.path.insert(0, {str(ROOT / 'app')!r})\n"
            "out = {}\n"
            "for name in ('outpost_updater', 'outpost_health', 'outpost_web', 'outpost_map', 'outpost_sensors',"
            " 'outpost_community', 'outpost_server'):\n"
            "    module = importlib.import_module(name)\n"
            "    for key, value in vars(module).items():\n"
            "        if key.isupper() and isinstance(value, (str, int, float, bool, tuple, list, type(None))):\n"
            "            out[name + '.' + key] = value\n"
            "print(json.dumps(out, default=str, sort_keys=True))\n"
        )
        names = {name for name, _, _ in build.settings()}
        base = {key: value for key, value in os.environ.items() if not key.startswith("OUTPOST_")}

        def run(environ):
            result = subprocess.run([sys.executable, "-c", code], env=environ, capture_output=True, text=True,
                                    timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            return json.loads(result.stdout.strip().splitlines()[-1])

        unset, empty = run(base), run({**base, **{name: "" for name in names}})
        self.assertGreater(len(unset), 50)
        self.assertEqual(empty, unset)


if __name__ == "__main__":
    unittest.main()
