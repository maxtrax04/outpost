#!/usr/bin/env bash
set -euo pipefail

python3 /app/outpost_web.py

echo "[Outpost] Generating initial weather data..."
python3 /app/outpost_updater.py || echo "[Outpost] Initial update failed; continuing."

echo "[Outpost] Starting update loop..."
python3 /app/outpost_updater.py --loop &

echo "[Outpost] Starting nginx..."
exec nginx -g "daemon off;"
