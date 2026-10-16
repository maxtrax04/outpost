import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers
import outpost_health as health


def good_payload(age_seconds=0):
    generated = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {"status": "ok", "provider": "mock", "location": "Test Site",
            "generated_at": generated.isoformat(), "current": {}, "forecast": []}


class HealthTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "weather.json"
        patcher = mock.patch.object(health, "DATA_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        print_patcher = mock.patch("builtins.print")
        print_patcher.start()
        self.addCleanup(print_patcher.stop)

    def run_check(self, payload=None, raw=None):
        if payload is not None:
            self.path.write_text(json.dumps(payload))
        if raw is not None:
            self.path.write_text(raw)
        return health.main()

    def test_healthy(self):
        self.assertEqual(self.run_check(good_payload()), 0)

    def test_missing_file(self):
        self.assertEqual(health.main(), 1)

    def test_invalid_json(self):
        self.assertEqual(self.run_check(raw="{not json"), 1)

    def test_missing_fields(self):
        payload = good_payload()
        del payload["location"]
        self.assertEqual(self.run_check(payload), 1)

    def test_current_must_be_an_object(self):
        payload = good_payload()
        payload["current"] = []
        self.assertEqual(self.run_check(payload), 1)

    def test_forecast_must_be_a_list(self):
        payload = good_payload()
        payload["forecast"] = {}
        self.assertEqual(self.run_check(payload), 1)

    def test_stale_data_is_unhealthy(self):
        self.assertEqual(self.run_check(good_payload(age_seconds=health.MAX_AGE_SECONDS + 60)), 1)

    def test_slightly_old_data_is_still_healthy(self):
        self.assertEqual(self.run_check(good_payload(age_seconds=health.MAX_AGE_SECONDS - 60)), 0)

    def test_bad_timestamp(self):
        payload = good_payload()
        payload["generated_at"] = "yesterday"
        self.assertEqual(self.run_check(payload), 1)


if __name__ == "__main__":
    unittest.main()
