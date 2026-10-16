#!/usr/bin/env bash
# Runs all tests inside Docker containers, so nothing needs to be installed.
# Usage: ./scripts/test.sh
set -euo pipefail

root="$(git rev-parse --show-toplevel)"

echo "== Python tests =="
docker run --rm -v "$root:/work" -w /work -e PYTHONDONTWRITEBYTECODE=1 \
  python:3.12-slim python -m unittest discover -s tests -b

echo "== JavaScript tests =="
docker run --rm -v "$root:/work" -w /work -e TZ=UTC \
  node:22-slim node --test tests/dim.test.js

echo "All tests passed."
