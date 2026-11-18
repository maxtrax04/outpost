// The map panel (docs/map-design.md): OpenStreetMap vector tiles (Shortbread schema), fetched
// through Outpost (/tiles/base/...) and drawn on a 2D canvas in the theme's colors and font.
// A fixed picture centered on the place shown, at OUTPOST_MAP_ZOOM: no panning, no library, no WebGL.
// The drawing helpers are pure, so they can be tested without a page.

(function (root) {
    "use strict";

    const TILE_SIZE = 256;
    const MAX_LATITUDE = 85.05112878;
    // Layers drawn, and so decoded (mvt.js skips the rest)
    const LAYERS = ["ocean", "water_polygons", "water_lines", "boundaries", "streets", "place_labels"];
    const DECODED_TILES_KEPT = 40;

    // Streets by importance: the lowest zoom each kind is drawn at, and its width in pixels there
    const STREETS = {
        motorway: { from: 5, width: 2 },
        trunk: { from: 6, width: 1.6 },
        primary: { from: 8, width: 1.3 },
        secondary: { from: 9, width: 1 },
        tertiary: { from: 11, width: 0.8 },
        unclassified: { from: 12, width: 0.6 },
        residential: { from: 12, width: 0.6 },
    };

    // Place names by importance: the lowest zoom each kind is named at, and its text size
    const PLACES = {
        capital: { from: 4, size: 13, rank: 0 },
        state_capital: { from: 5, size: 12.5, rank: 1 },
        city: { from: 5, size: 12, rank: 2 },
        town: { from: 8, size: 11, rank: 3 },
        village: { from: 10, size: 10.5, rank: 4 },
        suburb: { from: 11, size: 10.5, rank: 5 },
        hamlet: { from: 12, size: 10, rank: 6 },
    };

    // ---- Position --------------------------------------------------------------

    // A place's position in pixels on the whole world map at a zoom (Web Mercator)
    function worldPixel(latitude, longitude, zoom) {
        const size = TILE_SIZE * 2 ** zoom;
        const lat = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, latitude)) * Math.PI / 180;
        return {
            x: ((longitude + 180) / 360) * size,
            y: (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * size,
        };
    }

    // The tiles covering a width x height view centered on a place: [{ x, y, left, top }], where
    // x wraps around the date line and left/top are where the tile goes in the view
    function tilesFor(latitude, longitude, zoom, width, height) {
        const center = worldPixel(latitude, longitude, zoom);
        const left = center.x - width / 2;
        const top = center.y - height / 2;
        const count = 2 ** zoom;
        const tiles = [];
        for (let ty = Math.floor(top / TILE_SIZE); ty <= Math.floor((top + height - 1) / TILE_SIZE); ty += 1) {
            if (ty < 0 || ty >= count) continue;
            for (let tx = Math.floor(left / TILE_SIZE); tx <= Math.floor((left + width - 1) / TILE_SIZE); tx += 1) {
                tiles.push({
                    x: ((tx % count) + count) % count,
                    y: ty,
                    left: tx * TILE_SIZE - left,
                    top: ty * TILE_SIZE - top,
                });
            }
        }
        return tiles;
    }

    // ---- What to draw ------------------------------------------------------------

    function streetStyle(properties, zoom) {
        if (!properties || properties.rail || properties.tunnel) return null;
        const style = STREETS[properties.kind];
        if (!style || zoom < style.from) return null;
        const width = style.width * (1 + (zoom - style.from) * 0.15);
        return { width: properties.link ? width * 0.6 : width };
    }

    // Country borders solid, state or province borders dashed; none at sea
    function borderStyle(properties) {
        if (!properties || properties.maritime) return null;
        const level = Number(properties.admin_level);
        if (level === 2) return { width: 1.4, dash: [] };
        if (level === 4) return { width: 0.9, dash: [4, 3] };
        return null;
    }

    function placeStyle(properties, zoom) {
        const style = properties && PLACES[properties.kind];
        if (!style || zoom < style.from || typeof properties.name !== "string" || !properties.name.trim()) return null;
        return style;
    }

    // Labels in order: most important kind first, then the biggest places
    function sortLabels(labels) {
        return labels.slice().sort((a, b) => a.rank - b.rank || (b.population || 0) - (a.population || 0));
    }

    // Keeps the labels that fit without overlapping one already placed (boxes: { x, y, width, height })
    function placeLabels(labels, overlaps = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width
        && a.y < b.y + b.height && b.y < a.y + a.height) {
        const placed = [];
        const seen = new Set();
        for (const label of sortLabels(labels)) {
            const key = `${label.text}|${Math.round(label.box.x / 20)}|${Math.round(label.box.y / 20)}`;
            if (seen.has(key)) continue; // the same place from two tiles' edges
            if (placed.some((other) => overlaps(label.box, other.box))) continue;
            seen.add(key);
            placed.push(label);
        }
        return placed;
    }

    function insideView(box, width, height) {
        return box.x >= 0 && box.y >= 0 && box.x + box.width <= width && box.y + box.height <= height;
    }

    // ---- Drawing ---------------------------------------------------------------------

    function tracePath(context, parts, scale, left, top) {
        for (const part of parts) {
            part.forEach(([x, y], index) => {
                const px = left + x * scale;
                const py = top + y * scale;
                if (index === 0) context.moveTo(px, py);
                else context.lineTo(px, py);
            });
        }
    }

    function eachFeature(tile, layerName, draw) {
        const layer = tile.data && tile.data[layerName];
        if (!layer) return;
        const scale = TILE_SIZE / (layer.extent || 4096);
        for (const feature of layer.features) draw(feature, scale);
    }

    // Draws decoded tiles ([{ left, top, data }]) on a 2D context of width x height (CSS pixels).
    // colors: { land, water, road, border, label, halo, marker }; font: a CSS font-family.
    // The radar goes between the two layers: drawBase under it, drawOverlay on top.
    function draw(context, tiles, options) {
        drawBase(context, tiles, options);
        return drawOverlay(context, tiles, options);
    }

    // The map under the radar: land, water, rivers, streets, and borders
    function drawBase(context, tiles, options) {
        const { width, height, zoom, colors } = options;
        context.save();
        context.fillStyle = colors.land;
        context.fillRect(0, 0, width, height);
        context.lineJoin = "round";
        context.lineCap = "round";

        // Water, then rivers, borders, and streets, each across every tile so they join up
        context.fillStyle = colors.water;
        for (const tile of tiles) {
            for (const name of ["ocean", "water_polygons"]) {
                eachFeature(tile, name, (feature, scale) => {
                    if (feature.type !== "polygon") return;
                    context.beginPath();
                    tracePath(context, feature.geometry, scale, tile.left, tile.top);
                    context.fill("evenodd");
                });
            }
        }

        context.strokeStyle = colors.water;
        for (const tile of tiles) {
            eachFeature(tile, "water_lines", (feature, scale) => {
                if (feature.type !== "line" || !["river", "canal"].includes(feature.properties.kind)) return;
                context.lineWidth = zoom >= 12 ? 1.5 : 1;
                context.beginPath();
                tracePath(context, feature.geometry, scale, tile.left, tile.top);
                context.stroke();
            });
        }

        context.strokeStyle = colors.road;
        for (const tile of tiles) {
            eachFeature(tile, "streets", (feature, scale) => {
                const style = feature.type === "line" && streetStyle(feature.properties, zoom);
                if (!style) return;
                context.lineWidth = style.width;
                context.beginPath();
                tracePath(context, feature.geometry, scale, tile.left, tile.top);
                context.stroke();
            });
        }

        context.strokeStyle = colors.border;
        for (const tile of tiles) {
            eachFeature(tile, "boundaries", (feature, scale) => {
                const style = feature.type === "line" && borderStyle(feature.properties);
                if (!style) return;
                context.lineWidth = style.width;
                context.setLineDash(style.dash);
                context.beginPath();
                tracePath(context, feature.geometry, scale, tile.left, tile.top);
                context.stroke();
            });
        }
        context.setLineDash([]);
        context.restore();
    }

    // What goes over the radar: the place shown, and place names. Returns how many were named.
    function drawOverlay(context, tiles, options) {
        const { width, height, zoom, colors, font } = options;
        context.save();
        context.lineJoin = "round";
        context.lineCap = "round";

        // The place shown: a ring at the center
        context.strokeStyle = colors.marker;
        context.lineWidth = 2;
        context.beginPath();
        context.arc(width / 2, height / 2, 6, 0, Math.PI * 2);
        context.stroke();
        context.fillStyle = colors.marker;
        context.beginPath();
        context.arc(width / 2, height / 2, 2, 0, Math.PI * 2);
        context.fill();

        // Place names last, on top, without overlaps (and never over the marker)
        const labels = [];
        for (const tile of tiles) {
            eachFeature(tile, "place_labels", (feature, scale) => {
                const style = feature.type === "point" && placeStyle(feature.properties, zoom);
                if (!style) return;
                for (const [x, y] of feature.geometry[0] || []) {
                    const px = tile.left + x * scale;
                    const py = tile.top + y * scale;
                    if (px < 0 || py < 0 || px > width || py > height) continue;
                    const text = feature.properties.name.trim();
                    context.font = `${style.size}px ${font}`;
                    const textWidth = context.measureText(text).width;
                    const box = { x: px - textWidth / 2 - 2, y: py - style.size - 6, width: textWidth + 4, height: style.size + 4 };
                    if (!insideView(box, width, height)) continue; // never a name cut off at the edge
                    labels.push({ text, size: style.size, rank: style.rank, population: feature.properties.population, px, py, box });
                }
            });
        }
        const marker = { text: "", rank: -1, box: { x: width / 2 - 9, y: height / 2 - 9, width: 18, height: 18 } };
        const placed = placeLabels([marker, ...labels]).filter((label) => label !== marker);
        context.textAlign = "center";
        context.textBaseline = "alphabetic";
        context.lineWidth = 3;
        context.strokeStyle = colors.halo;
        context.fillStyle = colors.label;
        for (const label of placed) {
            context.font = `${label.size}px ${font}`;
            context.fillRect(label.px - 1, label.py - 1, 2, 2);
            context.strokeText(label.text, label.px, label.py - 5);
            context.fillText(label.text, label.px, label.py - 5);
        }
        context.restore();
        return placed.length;
    }

    // ---- The panel ---------------------------------------------------------------

    // Decoded tiles, so redrawing (a resize, a theme change) does not fetch or decode again
    const decoded = new Map();

    async function loadTile(zoom, x, y, fetchFn) {
        const key = `${zoom}/${x}/${y}`;
        if (decoded.has(key)) {
            const data = decoded.get(key);
            decoded.delete(key);
            decoded.set(key, data); // most recently used last
            return data;
        }
        const response = await fetchFn(`tiles/base/${key}.mvt`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = root.OutpostMvt.decode(await response.arrayBuffer(), LAYERS);
        decoded.set(key, data);
        while (decoded.size > DECODED_TILES_KEPT) decoded.delete(decoded.keys().next().value);
        return data;
    }

    // A color from a CSS custom property, resolved (color-mix() and var() included) to one a canvas
    // understands; fallback when the browser cannot resolve it
    function cssColor(style, name, fallback, probe) {
        const value = style.getPropertyValue(name).trim();
        if (!value || (root.CSS && root.CSS.supports && !root.CSS.supports("color", value))) return fallback;
        if (!probe) return value;
        probe.style.setProperty("color", value);
        return getComputedStyle(probe).color || fallback;
    }

    function themeColors(element) {
        const style = getComputedStyle(element);
        const probe = document.createElement("span");
        probe.hidden = true;
        element.appendChild(probe);
        const text = cssColor(style, "--text", "#cccccc", probe);
        const background = cssColor(style, "--bg", "#000000", probe);
        const colors = {
            land: cssColor(style, "--map-land", background, probe),
            water: cssColor(style, "--map-water", "#1d3b4a", probe),
            road: cssColor(style, "--map-road", text, probe),
            border: cssColor(style, "--map-border", text, probe),
            label: cssColor(style, "--map-label", text, probe),
            marker: cssColor(style, "--map-marker", text, probe),
        };
        colors.halo = cssColor(style, "--map-halo", colors.land, probe);
        probe.remove();
        return colors;
    }

    let shownKey = "";
    let drawing = 0;

    // Draws the map in canvas for place at zoom, unless it already shows exactly that.
    // Returns "drawn", "unchanged", or "failed".
    async function show(canvas, place, zoom, options = {}) {
        const box = canvas.getBoundingClientRect();
        const width = Math.round(box.width);
        const height = Math.round(box.height);
        if (!width || !height || !place) return "unchanged";
        const theme = document.documentElement.dataset.theme || "";
        const key = [place.latitude.toFixed(4), place.longitude.toFixed(4), zoom, width, height, theme,
            document.documentElement.dataset.effects || ""].join("|");
        if (key === shownKey && !options.force) return "unchanged";
        const number = ++drawing;

        const fetchFn = options.fetchFn || ((url) => fetch(url));
        const needed = tilesFor(place.latitude, place.longitude, zoom, width, height);
        const results = await Promise.allSettled(needed.map((tile) => loadTile(zoom, tile.x, tile.y, fetchFn)));
        if (number !== drawing) return "unchanged"; // a newer drawing has started
        const tiles = needed.map((tile, index) => ({ ...tile, data: results[index].status === "fulfilled" ? results[index].value : null }));
        if (!tiles.some((tile) => tile.data)) return "failed";

        const ratio = Math.min(root.devicePixelRatio || 1, 3);
        const pixelWidth = Math.round(width * ratio);
        const pixelHeight = Math.round(height * ratio);
        const font = getComputedStyle(canvas).fontFamily || "sans-serif";
        const drawOptions = { width, height, zoom, colors: themeColors(canvas.closest(".panel") || document.body), font };
        const base = layerCanvas(pixelWidth, pixelHeight);
        const overlay = layerCanvas(pixelWidth, pixelHeight);
        for (const [layer, drawLayer] of [[base, drawBase], [overlay, drawOverlay]]) {
            const context = layer.getContext("2d");
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            drawLayer(context, tiles, drawOptions);
        }
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
        // The same place and size (a theme change) keeps the radar; anything else needs it drawn again
        const viewKey = [place.latitude.toFixed(4), place.longitude.toFixed(4), zoom, width, height, ratio].join("|");
        const radar = shown && shown.canvas === canvas && shown.view.key === viewKey ? shown.radar : null;
        shown = { canvas, base, overlay, radar, view: { place: { ...place }, zoom, width, height, ratio, key: viewKey } };
        compose();
        shownKey = tiles.every((tile) => tile.data) ? key : ""; // try a missing tile again next time
        return "drawn";
    }

    // ---- Layers --------------------------------------------------------------------
    // The base map and its names are drawn once into layers of their own, so a new radar frame
    // (or a loop of them) only puts the three layers together again.

    const RADAR_OPACITY = 0.75;
    let shown = null; // { canvas, base, overlay, radar, view }

    function layerCanvas(width, height) {
        const layer = document.createElement("canvas");
        layer.width = width;
        layer.height = height;
        return layer;
    }

    function compose() {
        if (!shown) return;
        const { canvas, base, overlay, radar } = shown;
        const context = canvas.getContext("2d");
        context.setTransform(1, 0, 0, 1, 0, 0);
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.drawImage(base, 0, 0);
        if (radar) {
            context.globalAlpha = RADAR_OPACITY;
            context.drawImage(radar, 0, 0, canvas.width, canvas.height);
            context.globalAlpha = 1;
        }
        context.drawImage(overlay, 0, 0);
    }

    // The map's place, zoom, and size (CSS pixels, and device pixels per CSS pixel), with a key
    // that changes when any of them does; null before the map is drawn
    function view() {
        return shown ? { ...shown.view, place: { ...shown.view.place } } : null;
    }

    // Shows a radar layer (a canvas the size of the map, in device pixels), or none
    function setRadar(layer) {
        if (!shown) return;
        shown.radar = layer || null;
        compose();
    }

    const api = { TILE_SIZE, LAYERS, STREETS, PLACES, RADAR_OPACITY, worldPixel, tilesFor, streetStyle, borderStyle,
        placeStyle, insideView, sortLabels, placeLabels, draw, drawBase, drawOverlay, show, view, setRadar };

    root.OutpostMap = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
