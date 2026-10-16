"""Shared test setup. Import this module first in every test file."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The updater reads its settings when it is imported, so set made-up values
# first. Tests never use a real location.
os.environ["OUTPOST_PROVIDER"] = "mock"
os.environ["OUTPOST_LATITUDE"] = "10.0"
os.environ["OUTPOST_LONGITUDE"] = "20.0"
os.environ["OUTPOST_LOCATION_NAME"] = "Test Site"
os.environ["OUTPOST_THEME"] = "retro-crt"

sys.path.insert(0, str(APP_DIR))


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
