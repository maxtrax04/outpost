"""
weather.json matches its documented format (docs/schema/weather-v1.json and docs/data-format.md).

The image has no pip, so this checks the schema with a small validator for the parts of JSON
Schema the file uses, rather than a library.
"""

import json
import re
import unittest
from unittest import mock

import helpers
from helpers import ROOT

import outpost_updater as u
from providers import openmeteo
from test_updater import nws_data, openmeteo_data

SCHEMA = json.loads((ROOT / "docs" / "schema" / "weather-v1.json").read_text(encoding="utf-8"))
SUPPORTED_KEYWORDS = {
    "$schema", "$id", "$ref", "$defs", "title", "description", "type", "const", "enum", "required",
    "properties", "items", "anyOf", "minimum", "maximum", "format",
}
TYPES = {
    "object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool,
}


def type_matches(value, name):
    if name == "null":
        return value is None
    if isinstance(value, bool) and name != "boolean":
        return False
    return isinstance(value, TYPES[name])


def validate(value, schema, path="weather.json"):
    """Returns a list of problems (empty when value matches schema)."""
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        return validate(value, SCHEMA["$defs"][name], path)
    if "anyOf" in schema:
        if any(not validate(value, option, path) for option in schema["anyOf"]):
            return []
        return [f"{path} matches none of the allowed shapes: {value!r}"]

    problems = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type_matches(value, name) for name in names):
            return [f"{path} should be {' or '.join(names)}, not {value!r}"]
    if "const" in schema and value != schema["const"]:
        problems.append(f"{path} should be {schema['const']!r}, not {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path} should be one of {schema['enum']}, not {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path} is above {schema['maximum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path} is missing {key}")
        for key, child in schema.get("properties", {}).items():
            if key in value:
                problems.extend(validate(value[key], child, f"{path}.{key}"))
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            problems.extend(validate(item, schema["items"], f"{path}[{index}]"))
    return problems


def keywords(schema):
    """Every keyword used anywhere in the schema."""
    found = set()
    if isinstance(schema, dict):
        for key, child in schema.items():
            found.add(key)
            if key in ("properties", "$defs"):
                for grandchild in child.values():
                    found |= keywords(grandchild)
            elif key not in ("enum", "const", "required"):
                found |= keywords(child)
    elif isinstance(schema, list):
        for child in schema:
            found |= keywords(child)
    return found


class ValidatorTests(unittest.TestCase):
    """The small validator itself, so a passing check means something."""

    def test_the_schema_uses_only_keywords_the_validator_understands(self):
        self.assertLessEqual(keywords(SCHEMA), SUPPORTED_KEYWORDS)

    def test_it_finds_problems(self):
        payload = u.build_mock_payload()
        payload["schema_version"] = 2
        del payload["units"]["speed"]
        payload["current"]["temperature"] = "70"
        payload["current"]["icon"] = "tornado"
        payload["forecast"][0]["precipitation_chance"] = 140
        payload["sources"]["weather"] = {"id": "mock"}
        problems = " | ".join(validate(payload, SCHEMA))
        for expected in ("schema_version", "units is missing speed", "current.temperature", "current.icon",
                         "precipitation_chance is above", "sources.weather"):
            with self.subTest(expected=expected):
                self.assertIn(expected, problems)


class PayloadTests(unittest.TestCase):
    def assertValid(self, payload):
        self.assertEqual(validate(payload, SCHEMA), [])

    def test_mock_data(self):
        with mock.patch.dict("os.environ", {"OUTPOST_MOCK_ALERTS": "true"}):
            for _ in range(20):
                self.assertValid(u.build_mock_payload())

    def test_error_data(self):
        self.assertValid(u.build_error_payload("boom"))

    def test_open_meteo_data(self):
        self.assertValid(u.build_live_payload("openmeteo", openmeteo_data()))

    def test_nws_data(self):
        self.assertValid(u.build_live_payload("nws", nws_data()))

    def test_gap_filled_data(self):
        data, filled = u.gapfill.fill(nws_data(), openmeteo_data())
        data["fill"] = u.source_entry("openmeteo", openmeteo.SOURCE, fields=filled)
        payload = u.build_live_payload("nws", data)
        self.assertTrue(payload["sources"]["fill"]["fields"])
        self.assertValid(payload)

    def test_the_file_links_to_the_schema_for_its_version(self):
        payload = u.build_mock_payload()
        self.assertEqual(payload["$schema"], SCHEMA["$id"])
        version = payload["schema_version"]
        self.assertTrue(payload["$schema"].endswith(f"/docs/schema/weather-v{version}.json"))
        self.assertTrue((ROOT / "docs" / "schema" / f"weather-v{version}.json").exists())
        self.assertTrue(payload["$schema"].startswith("https://raw.githubusercontent.com/maxtrax04/outpost/main/"))

    def test_schema_version_matches_the_updater(self):
        self.assertEqual(SCHEMA["properties"]["schema_version"]["const"], u.SCHEMA_VERSION)

    def test_schema_requires_every_field_the_updater_writes(self):
        payload = u.build_mock_payload()
        self.assertEqual(set(SCHEMA["required"]), set(payload))
        self.assertEqual(set(SCHEMA["properties"]["current"]["required"]), set(payload["current"]))
        self.assertEqual(set(SCHEMA["properties"]["forecast"]["items"]["required"]), set(payload["forecast"][0]))

    def test_icons_match_the_icon_files(self):
        icons = {path.stem for path in (ROOT / "assets" / "icons").glob("*.svg")}
        self.assertEqual(set(SCHEMA["$defs"]["icon"]["enum"]), icons)


class DocumentationTests(unittest.TestCase):
    def test_every_field_is_documented(self):
        doc = (ROOT / "docs" / "data-format.md").read_text(encoding="utf-8")
        payload = u.build_mock_payload()
        names = (list(payload) + list(payload["units"]) + list(payload["current"]) + list(payload["forecast"][0])
                 + ["weather", "alerts", "fill", "fields", "title", "description", "severity", "expires", "uri"])
        for name in names:
            with self.subTest(name=name):
                self.assertRegex(doc, rf"`{re.escape(name)}`")

    def test_the_documented_version_matches(self):
        doc = (ROOT / "docs" / "data-format.md").read_text(encoding="utf-8")
        self.assertIn(f'"schema_version": {u.SCHEMA_VERSION}', doc)


if __name__ == "__main__":
    unittest.main()
