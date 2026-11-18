// Tests for web/radar.js: what the radar asks for, where its tiles go, and when it loops.
// Run with: node --test tests/radar.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const realMap = require("../web/map.js");
const radar = require("../web/radar.js");

// A frame every 10 minutes from 08:00 to 10:00, named as the server names NOAA's (20270115T080000Z)
const FRAMES = Array.from({ length: 13 }, (_, index) => {
    const time = new Date(Date.UTC(2027, 0, 15, 8, index * 10)).toISOString().replace(".000", "");
    return { time, tiles: `tiles/radar/noaa/conus/${time.replace(/[-:]/g, "")}/{z}/{x}/{y}.png` };
});
const ANSWER = { source: "noaa", credit: "NOAA", credit_url: "https://www.nssl.noaa.gov/projects/mrms/", zoom: 7, frames: FRAMES };

// ---- Helpers ------------------------------------------------------------------------

test("the frame list for home or a chosen place, rounded as the API rounds", () => {
    assert.strictEqual(radar.listUrl(null), "api/radar");
    assert.strictEqual(radar.listUrl({ latitude: 12.3456, longitude: -45.6789 }), "api/radar?lat=12.35&lon=-45.68");
});

test("only tile addresses on Outpost are used", () => {
    const answer = radar.validAnswer({ ...ANSWER, frames: [
        ...FRAMES.slice(-1),
        { time: "2027-01-15T10:00:00Z", tiles: "https://evil.example/{z}/{x}/{y}.png" },
        { time: "2027-01-15T10:00:00Z", tiles: "tiles/radar/../../api/x/{z}/{x}/{y}.png" },
        { time: "never", tiles: FRAMES[0].tiles },
    ] });
    assert.strictEqual(answer.frames.length, 1);
    assert.ok(answer.frames[0].time instanceof Date);
    assert.strictEqual(answer.creditUrl, ANSWER.credit_url);
    assert.strictEqual(radar.validAnswer({ ...ANSWER, credit_url: "javascript:alert(1)" }).creditUrl, "");
    assert.strictEqual(radar.validAnswer({ ...ANSWER, frames: [] }), null);
    assert.strictEqual(radar.validAnswer({ ...ANSWER, zoom: "near" }), null);
    assert.strictEqual(radar.validAnswer(null), null);
});

test("tile addresses", () => {
    assert.strictEqual(radar.tileUrl(FRAMES[0].tiles, 7, 29, 48), "tiles/radar/noaa/conus/20270115T080000Z/7/29/48.png");
});

test("the loop plays only when asked for, with full effects, and not on ePaper", () => {
    assert.strictEqual(radar.loopPlays({ radar_loop: true }, "full", "retro-crt"), true);
    assert.strictEqual(radar.loopPlays({ radar_loop: false }, "full", "retro-crt"), false);
    assert.strictEqual(radar.loopPlays({ radar_loop: true }, "reduced", "retro-crt"), false);
    assert.strictEqual(radar.loopPlays({ radar_loop: true }, "full", "ink"), false);
    assert.strictEqual(radar.delayAfter(12, 13), radar.HOLD_MS);
    assert.strictEqual(radar.delayAfter(3, 13), radar.FRAME_MS);
});

test("radar tiles line up with the map, and are drawn larger past the radar's zoom", () => {
    const view = { place: { latitude: 0, longitude: 0 }, zoom: 2, width: 256, height: 256 };
    const same = radar.layout(view, 2);
    assert.deepStrictEqual(same.map((tile) => [tile.x, tile.y, tile.left, tile.top, tile.size]),
        realMap.tilesFor(0, 0, 2, 256, 256).map((tile) => [tile.x, tile.y, tile.left, tile.top, 256]));
    // The map at zoom 9, the radar at 7: each radar tile covers 4 x 4 map tiles
    const larger = radar.layout({ place: { latitude: 0, longitude: 0 }, zoom: 9, width: 800, height: 400 }, 7);
    assert.ok(larger.every((tile) => tile.size === 1024));
    assert.deepStrictEqual(larger.map((tile) => [tile.x, tile.y]), [[63, 63], [64, 63], [63, 64], [64, 64]]);
    assert.deepStrictEqual([larger[0].left, larger[0].top], [400 - 1024, 200 - 1024]);
});

// ---- Showing it on a page -----------------------------------------------------------

let pages = 0;

function fakePage(t) {
    const loaded = [];
    const layers = [];
    globalThis.document = {
        createElement: () => {
            const drawn = [];
            const layer = { drawn, getContext: () => ({ drawImage: (image, ...at) => drawn.push([image.src, ...at]) }) };
            return layer;
        },
    };
    globalThis.Image = class {
        set src(value) {
            this.url = value;
            loaded.push(value);
            setImmediate(() => (value.includes("/missing/") ? this.onerror() : this.onload()));
        }
        get src() {
            return this.url;
        }
    };
    const view = { place: { latitude: 39, longitude: -98 }, zoom: 7, width: 512, height: 256, ratio: 1, key: `view-${pages += 1}` };
    globalThis.OutpostMap = { ...realMap, view: () => view, setRadar: (layer) => layers.push(layer) };
    t.after(() => {
        radar.stop();
        globalThis.OutpostMap = realMap;
        delete globalThis.document;
        delete globalThis.Image;
    });
    return { loaded, layers, view };
}

function fetcher(answer, calls = []) {
    return async (url) => {
        calls.push(url);
        if (!answer) return { ok: false, status: 502, json: async () => ({}) };
        return { ok: true, status: 200, json: async () => answer };
    };
}

test("the latest frame is shown, with its credit and time", async (t) => {
    const page = fakePage(t);
    const shown = [];
    const calls = [];
    const result = await radar.update({ map: { radar: true }, place: null, effects: "full", theme: "retro-crt",
        fetchFn: fetcher(ANSWER, calls), now: 1, onFrame: (frame) => shown.push(frame) });
    assert.strictEqual(result.status, "shown");
    assert.strictEqual(result.credit, "NOAA");
    assert.deepStrictEqual(calls, ["api/radar"]);
    assert.strictEqual(page.layers.length, 1);
    assert.ok(page.loaded.length > 0 && page.loaded.every((url) => url.startsWith("tiles/radar/noaa/conus/20270115T100000Z/7/")));
    assert.strictEqual(shown[0].time.toISOString(), "2027-01-15T10:00:00.000Z");

    // Nothing new a minute later: the list is not asked for again, nothing is redrawn
    const again = await radar.update({ map: { radar: true }, place: null, fetchFn: fetcher(ANSWER, calls), now: 60001 });
    assert.strictEqual(again.status, "shown");
    assert.deepStrictEqual(calls, ["api/radar"]);
    assert.strictEqual(page.layers.length, 1);
    // A new list after a couple of minutes
    await radar.update({ map: { radar: true }, place: null, fetchFn: fetcher(ANSWER, calls), now: 1 + radar.LIST_REFRESH_MS });
    assert.strictEqual(calls.length, 2);
});

test("radar off, or unavailable, leaves the map without it", async (t) => {
    const page = fakePage(t);
    assert.strictEqual((await radar.update({ map: { radar: false } })).status, "off");
    assert.deepStrictEqual(page.layers, [null]);
    const result = await radar.update({ map: { radar: true }, place: { latitude: 48.9, longitude: 2.3 },
        fetchFn: fetcher(null), now: 10 });
    assert.strictEqual(result.status, "unavailable");
    assert.deepStrictEqual(page.layers, [null, null]);
});

test("the loop plays every frame, then holds on the latest", async (t) => {
    const page = fakePage(t);
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const shown = [];
    await radar.update({ map: { radar: true, radar_loop: true }, place: { latitude: 1, longitude: 2 }, effects: "full",
        theme: "modern-dark", fetchFn: fetcher(ANSWER), now: 1e9, onFrame: (frame) => shown.push(frame) });
    // Let the frames load (each image answers on the next turn)
    for (let i = 0; i < 40; i += 1) await new Promise((resolve) => setImmediate(resolve));
    assert.strictEqual(new Set(page.loaded.map((url) => url.split("/")[4])).size, 13);
    t.mock.timers.tick(radar.HOLD_MS);
    t.mock.timers.tick(radar.FRAME_MS);
    assert.strictEqual(shown.length, 3);
    assert.strictEqual(shown[1].time.toISOString(), "2027-01-15T08:00:00.000Z");
    assert.strictEqual(shown[2].time.toISOString(), "2027-01-15T08:10:00.000Z");
    // Reduced effects stop it at the latest frame
    await radar.update({ map: { radar: true, radar_loop: true }, place: { latitude: 1, longitude: 2 }, effects: "reduced",
        theme: "modern-dark", fetchFn: fetcher(ANSWER), now: 1e9 + 1, onFrame: (frame) => shown.push(frame) });
    const count = shown.length;
    t.mock.timers.tick(radar.HOLD_MS * 5);
    assert.strictEqual(shown.length, count);
    assert.strictEqual(shown[count - 1].time.toISOString(), "2027-01-15T10:00:00.000Z");
});

test("a tile that failed is tried again next time", async (t) => {
    const page = fakePage(t);
    const answer = { ...ANSWER, frames: [{ time: FRAMES[0].time, tiles: "tiles/radar/noaa/missing/x1/{z}/{x}/{y}.png" }] };
    await radar.update({ map: { radar: true }, place: null, fetchFn: fetcher(answer), now: 5e9 });
    const first = page.loaded.length;
    await radar.update({ map: { radar: true }, place: null, fetchFn: fetcher(answer), now: 5e9 + 1 });
    assert.strictEqual(page.loaded.length, first * 2);
    assert.strictEqual(page.layers.length, 2);
});
