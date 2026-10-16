import unittest

import helpers
from providers import gapfill


def nws_like():
    return {
        "current": {"humidity_percent": 20, "wind_mph": 5, "pressure_inhg": 30.0, "uv_index": None, "visibility_miles": 10.0},
        "forecast": [
            {"day": "2026-07-15", "high_f": None, "low_f": 60, "uv_index": None},
            {"day": "2026-07-16", "high_f": 85, "low_f": 59, "uv_index": None},
        ],
    }


def backup():
    return {
        "current": {"humidity_percent": 99, "wind_mph": 99, "pressure_inhg": 99.0, "uv_index": 4, "visibility_miles": 99.0},
        "forecast": [
            {"day": "2026-07-15", "high_f": 90, "low_f": 1, "uv_index": 7},
            {"day": "2026-07-16", "high_f": 1, "low_f": 1, "uv_index": 6},
        ],
    }


class GapFillTests(unittest.TestCase):
    def test_detects_gaps(self):
        self.assertTrue(gapfill.has_gaps(nws_like()))

    def test_no_gaps(self):
        full, _ = gapfill.fill(nws_like(), backup())
        self.assertFalse(gapfill.has_gaps(full))

    def test_fills_only_what_is_missing(self):
        merged, filled = gapfill.fill(nws_like(), backup())
        self.assertEqual(merged["current"]["uv_index"], 4)
        self.assertEqual(merged["forecast"][0]["high_f"], 90)
        self.assertEqual([d["uv_index"] for d in merged["forecast"]], [7, 6])

    def test_never_overwrites_existing_values(self):
        merged, _ = gapfill.fill(nws_like(), backup())
        self.assertEqual(merged["current"]["humidity_percent"], 20)
        self.assertEqual(merged["current"]["pressure_inhg"], 30.0)
        self.assertEqual(merged["forecast"][0]["low_f"], 60)
        self.assertEqual(merged["forecast"][1]["high_f"], 85)

    def test_reports_what_was_filled(self):
        _, filled = gapfill.fill(nws_like(), backup())
        self.assertEqual(filled, ["current.uv_index", "forecast.high_f", "forecast.uv_index"])

    def test_original_is_not_modified(self):
        original = nws_like()
        gapfill.fill(original, backup())
        self.assertIsNone(original["current"]["uv_index"])

    def test_days_are_matched_by_date(self):
        other = backup()
        other["forecast"] = [{"day": "2030-01-01", "high_f": 1, "low_f": 1, "uv_index": 9}]
        _, filled = gapfill.fill(nws_like(), other)
        self.assertEqual(filled, ["current.uv_index"])

    def test_backup_with_missing_values_fills_nothing(self):
        empty = {"current": {}, "forecast": []}
        merged, filled = gapfill.fill(nws_like(), empty)
        self.assertEqual(filled, [])
        self.assertIsNone(merged["current"]["uv_index"])


if __name__ == "__main__":
    unittest.main()
