#!/usr/bin/env bash
# Retakes the README's screenshots (docs/images/themes/*.png and docs/images/phone.png) from a
# freshly built image: the mock data at the example location (Goodsprings, NV, never a real one),
# tidied into a likely day by tests/browser/take-screenshots.js, the map on, no night dimming, and
# the theme button hidden. Needs Docker and internet access (Playwright, and the
# OpenStreetMap tiles and radar the map shows).
#
#   scripts/screenshots.sh
set -euo pipefail

cd "$(dirname "$0")/.."
NAME=outpost-screenshots
OUT=docs/images
PLAYWRIGHT=1.49.1

cleanup() {
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker network rm "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker build -q -t "$NAME" . >/dev/null
docker network create "$NAME" >/dev/null
# Only the example location and settings; nothing from .env.
# The contact for the map's tile server is the project page.
docker run -d --name "$NAME" --network "$NAME" \
    -e OUTPOST_PROVIDER=mock -e OUTPOST_MOCK_ALERTS=true -e TZ=America/Los_Angeles -e OUTPOST_DIM_LEVEL=1 \
    -e OUTPOST_LOCATION_NAME="Goodsprings, NV" -e OUTPOST_LATITUDE=35.8319 -e OUTPOST_LONGITUDE=-115.4328 \
    -e OUTPOST_MAP=true -e OUTPOST_CONTACT=https://github.com/maxtrax04/outpost \
    -e OUTPOST_THEME_SWITCHER=false \
    "$NAME" >/dev/null

for _ in $(seq 1 30); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$NAME")" = healthy ] && break
    sleep 2
done

mkdir -p "$OUT/themes"
# Git Bash on Windows: Docker wants the Windows form of the path
HERE="$(pwd -W 2>/dev/null || pwd)"
MSYS_NO_PATHCONV=1 docker run --rm --network "$NAME" \
    -v "$HERE/tests/browser:/work:ro" -v "$HERE/$OUT:/out" -w /tmp \
    -e OUTPOST_URL="http://$NAME" -e SCREENSHOTS=/out \
    "mcr.microsoft.com/playwright:v$PLAYWRIGHT-noble" \
    sh -c "npm install --silent --no-save playwright@$PLAYWRIGHT >/dev/null 2>&1 && cp /work/take-screenshots.js . && node take-screenshots.js"
