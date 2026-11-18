// Rain radar on the map (docs/map-design.md): NOAA in the US, RainViewer elsewhere, both through
// Outpost (/api/radar lists the frames, /tiles/radar/... serves their tiles). It shows the latest
// frame, or with OUTPOST_MAP_RADAR_LOOP the past 2 hours as a loop, except on ePaper (the ink
// theme) and with reduced effects, which always get the latest frame alone.
// The helpers are pure, so they can be tested without a page; web/map.js draws the layers.

(function (root) {
    "use strict";

    // How often the list of frames is asked for again (the server keeps it for as long)
    const LIST_REFRESH_MS = 2 * 60 * 1000;
    // The loop: each frame for half a second, the latest for two
    const FRAME_MS = 500;
    const HOLD_MS = 2000;
    // Themes for screens that should never animate
    const STILL_THEMES = ["ink"];
    // Frames drawn and kept, so a loop is fetched and drawn once
    const LAYERS_KEPT = 14;
    const TILES_PATTERN = /^tiles\/radar\/[a-z]+(?:\/[a-z]+)?\/[A-Za-z0-9]{1,40}\/\{z\}\/\{x\}\/\{y\}\.png$/;

    // ---- Helpers ----------------------------------------------------------------------

    // /api/radar for home (place null) or for a chosen place, rounded as the API rounds it
    function listUrl(place) {
        if (!place) return "api/radar";
        return `api/radar?lat=${place.latitude.toFixed(2)}&lon=${place.longitude.toFixed(2)}`;
    }

    // The answer from /api/radar with anything unexpected left out, or null if nothing is usable
    function validAnswer(answer) {
        if (!answer || typeof answer !== "object" || !Array.isArray(answer.frames)) return null;
        const zoom = Number(answer.zoom);
        if (!Number.isInteger(zoom) || zoom < 0 || zoom > 20) return null;
        const frames = answer.frames
            .filter((frame) => frame && typeof frame.tiles === "string" && TILES_PATTERN.test(frame.tiles)
                && typeof frame.time === "string" && !Number.isNaN(Date.parse(frame.time)))
            .map((frame) => ({ time: new Date(frame.time), tiles: frame.tiles }));
        if (!frames.length) return null;
        return {
            source: typeof answer.source === "string" ? answer.source : "",
            credit: typeof answer.credit === "string" ? answer.credit : "",
            creditUrl: typeof answer.credit_url === "string" && /^https:\/\//.test(answer.credit_url) ? answer.credit_url : "",
            zoom,
            frames,
        };
    }

    function tileUrl(template, z, x, y) {
        return template.replace("{z}", z).replace("{x}", x).replace("{y}", y);
    }

    function loopPlays(mapConfig, effects, theme) {
        return Boolean(mapConfig && mapConfig.radar_loop) && effects !== "reduced" && !STILL_THEMES.includes(theme);
    }

    // The radar tiles under a map view ({ place, zoom, width, height }), at tileZoom: drawn larger
    // (size, in CSS pixels) when the map is zoomed in further than the radar goes
    function layout(view, tileZoom) {
        const map = root.OutpostMap;
        const scale = 2 ** Math.max(0, view.zoom - tileZoom);
        return map.tilesFor(view.place.latitude, view.place.longitude, tileZoom, view.width / scale, view.height / scale)
            .map((tile) => ({ x: tile.x, y: tile.y, left: tile.left * scale, top: tile.top * scale, size: map.TILE_SIZE * scale }));
    }

    function delayAfter(index, count) {
        return index >= count - 1 ? HOLD_MS : FRAME_MS;
    }

    // ---- Showing it -------------------------------------------------------------------

    // loop: which loop may run (stop() ends the one playing); updating: the newest update() call
    const state = { url: "", answer: null, fetchedAt: 0, layers: new Map(), signature: "", timer: null, loop: 0 };
    let updating = 0;

    function stop() {
        clearTimeout(state.timer);
        state.timer = null;
        state.loop += 1;
    }

    async function fetchList(url, fetchFn, now) {
        if (url === state.url && state.answer && now - state.fetchedAt < LIST_REFRESH_MS) return state.answer;
        const response = await fetchFn(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const answer = validAnswer(await response.json());
        if (!answer) throw new Error("No radar frames");
        Object.assign(state, { url, answer, fetchedAt: now });
        return answer;
    }

    function loadImage(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error("Radar tile failed"));
            image.src = url;
        });
    }

    // A frame drawn into a layer the size of the map, in CSS pixels (radar is soft anyway, and
    // this keeps a loop's layers small). Tiles that fail are left out and tried again next time.
    async function frameLayer(frame, answer, view) {
        const key = `${frame.tiles}|${view.key}`;
        if (state.layers.has(key)) return { layer: state.layers.get(key), complete: true };
        const tiles = layout(view, answer.zoom);
        const images = await Promise.allSettled(tiles.map((tile) => loadImage(tileUrl(frame.tiles, answer.zoom, tile.x, tile.y))));
        const layer = document.createElement("canvas");
        layer.width = view.width;
        layer.height = view.height;
        const context = layer.getContext("2d");
        let complete = true;
        images.forEach((result, index) => {
            const tile = tiles[index];
            if (result.status === "fulfilled") context.drawImage(result.value, tile.left, tile.top, tile.size, tile.size);
            else complete = false;
        });
        if (complete) {
            state.layers.set(key, layer);
            while (state.layers.size > LAYERS_KEPT) state.layers.delete(state.layers.keys().next().value);
        }
        return { layer, complete };
    }

    // Loads every frame (oldest first), then plays them until something changes
    async function play(frames, answer, view, onFrame) {
        const loop = state.loop;
        const layers = [];
        for (const frame of frames) {
            if (loop !== state.loop) return;
            layers.push((await frameLayer(frame, answer, view)).layer);
        }
        let index = layers.length - 1;
        const step = () => {
            if (loop !== state.loop) return;
            index = (index + 1) % layers.length;
            root.OutpostMap.setRadar(layers[index]);
            onFrame(frames[index]);
            state.timer = setTimeout(step, delayAfter(index, layers.length));
        };
        state.timer = setTimeout(step, HOLD_MS);
    }

    // Shows the radar on the map as it is drawn now. options: { map (config.map), place (the chosen
    // place, null for home), effects, theme, onFrame(frame), fetchFn, now }.
    // Returns { status: "off" | "shown" | "unavailable" | "stale", credit, creditUrl, frame }.
    async function update(options) {
        const map = root.OutpostMap;
        const view = map.view();
        const onFrame = options.onFrame || (() => {});
        if (!options.map || !options.map.radar || !view) {
            stop();
            state.signature = "";
            if (view) map.setRadar(null);
            return { status: "off" };
        }
        const number = ++updating;
        const fetchFn = options.fetchFn || ((url) => fetch(url));
        let answer;
        try {
            answer = await fetchList(listUrl(options.place), fetchFn, options.now || Date.now());
        } catch (error) {
            if (number !== updating) return { status: "stale" };
            stop();
            state.signature = "";
            map.setRadar(null);
            return { status: "unavailable" };
        }
        if (number !== updating) return { status: "stale" };

        const looping = loopPlays(options.map, options.effects, options.theme);
        const frames = looping ? answer.frames : answer.frames.slice(-1);
        const latest = frames[frames.length - 1];
        const shown = { status: "shown", credit: answer.credit, creditUrl: answer.creditUrl, frame: latest };
        const signature = [view.key, looping, frames.map((frame) => frame.tiles).join(",")].join("|");
        if (signature === state.signature) return shown; // nothing new: the frame (or loop) on screen carries on
        stop();
        const { layer, complete } = await frameLayer(latest, answer, view);
        if (number !== updating) return { status: "stale" };
        map.setRadar(layer);
        onFrame(latest);
        state.signature = complete ? signature : "";
        if (looping && frames.length > 1) play(frames, answer, view, onFrame).catch(() => stop());
        return shown;
    }

    const api = { LIST_REFRESH_MS, FRAME_MS, HOLD_MS, listUrl, validAnswer, tileUrl, loopPlays, layout, delayAfter, update, stop };

    root.OutpostRadar = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
