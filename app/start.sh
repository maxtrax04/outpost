#!/usr/bin/env bash
set -euo pipefail

# As a Home Assistant add-on: the add-on's options (and Home Assistant's home location, time
# zone, and units) become Outpost's settings, and nginx also listens for ingress
python3 /app/outpost_addon.py
if [ -f /run/outpost/addon.env ]; then
    # shellcheck source=/dev/null
    . /run/outpost/addon.env
fi

python3 /app/outpost_web.py

# Community themes (OUTPOST_COMMUNITY_THEMES): downloaded once per start, never required
python3 /app/outpost_community.py || true

echo "[Outpost] Generating initial weather data..."
python3 /app/outpost_updater.py || echo "[Outpost] Initial update failed; continuing."

echo "[Outpost] Starting the update loop and the API..."
python3 /app/outpost_server.py &

echo "[Outpost] Starting nginx..."
exec nginx -g "daemon off;"
