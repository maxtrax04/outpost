#!/usr/bin/env bash
set -euo pipefail

python3 /app/outpost_web.py

# Community themes (OUTPOST_COMMUNITY_THEMES): downloaded once per start, never required
python3 /app/outpost_community.py || true

echo "[Outpost] Generating initial weather data..."
python3 /app/outpost_updater.py || echo "[Outpost] Initial update failed; continuing."

echo "[Outpost] Starting update loop..."
python3 /app/outpost_updater.py --loop &

echo "[Outpost] Starting nginx..."
exec nginx -g "daemon off;"
