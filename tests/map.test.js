// Tests for web/mvt.js (decoding vector tiles) and web/map.js (what the map draws, and where).
// Run with: node --test tests/map.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const mvt = require("../web/mvt.js");
const map = require("../web/map.js");
const fixture = require("./browser/mvt-fixture.js");

// ---- Decoding --------------------------------------------------------------

test("a tile decodes to its layers, features, properties, and geometry", () => {
    const layers = mvt.decode(fixture.sampleTile());
    assert.deepStrictEqual(Object.keys(layers).sort(), ["boundaries", "buildings", "place_labels", "streets", "water_polygons"]);
    assert.strictEqual(layers.streets.extent, 2048);
    const [motorway, path] = layers.streets.features;
    assert.deepStrictEqual(motorway, { type: "line", properties: { kind: "motorway", bridge: false },
        geometry: [[[0, 1024], [2048, 1100]]] });
    assert.strictEqual(path.properties.kind, "path");
    const lake = layers.water_polygons.features[0];
    assert.strictEqual(lake.type, "polygon");
    // A closed ring ends where it started
    assert.deepStrictEqual(lake.geometry[0], [[100, 100], [900, 100], [900, 900], [100, 900], [100, 100]]);
    const town = layers.place_labels.features[0];
    assert.deepStrictEqual(town.properties, { kind: "city", name: "Cinder Flats", population: 5200 });
    assert.deepStrictEqual(town.geometry, [[[3000, 3000]]]);
    assert.strictEqual(layers.boundaries.features[0].properties.admin_level, 2);
});

test("only the wanted layers are decoded", () => {
    const layers = mvt.decode(fixture.sampleTile().buffer, map.LAYERS);
    assert.deepStrictEqual(Object.keys(layers).sort(), ["boundaries", "place_labels", "streets", "water_polygons"]);
});

test("every kind of value decodes", () => {
    const tile = fixture.encodeTile({ test: { features: [{ type: "point", geometry: [[[1, 2]]],
        properties: { text: "Dry Hollow", count: 3000000000, below: -42, ratio: 0.25, yes: true, no: false } }] } });
    assert.deepStrictEqual(mvt.decode(tile).test.features[0].properties,
        { text: "Dry Hollow", count: 3000000000, below: -42, ratio: 0.25, yes: true, no: false });
});

test("several parts and negative moves", () => {
    const parts = [[[10, 10], [5, 3]], [[4000, 4000], [4090, 3000], [100, 50]]];
    const tile = fixture.encodeTile({ lines: { features: [{ type: "line", properties: {}, geometry: parts }] } });
    assert.deepStrictEqual(mvt.decode(tile).lines.features[0].geometry, parts);
    assert.strictEqual(mvt.zigzag(3), -2);
    assert.strictEqual(mvt.zigzag(4), 2);
});

test("broken data is an error, not a hang", () => {
    const tile = fixture.sampleTile();
    assert.throws(() => mvt.decode(tile.slice(0, tile.length - 7)), /truncated/);
    assert.throws(() => mvt.decode(new Uint8Array([0x1a, 0xff])), /truncated/);
    assert.deepStrictEqual(mvt.decode(new Uint8Array([])), {});
    // An unknown geometry command stops that feature's geometry
    assert.deepStrictEqual(mvt.decodeGeometry([9, 2, 2, 5], "line"), [[[1, 1]]]);
});

// ---- Where -----------------------------------------------------------------------

test("positions on the world map", () => {
    const zero = map.worldPixel(0, 0, 0);
    assert.ok(Math.abs(zero.x - 128) < 1e-9 && Math.abs(zero.y - 128) < 1e-9);
    const corner = map.worldPixel(85.05112878, -180, 2);
    assert.ok(Math.abs(corner.x) < 1e-6 && Math.abs(corner.y) < 1e-3);
    // Beyond Web Mercator's edge is held at the edge
    assert.deepStrictEqual(map.worldPixel(89, 0, 1), map.worldPixel(85.05112878, 0, 1));
});

test("the tiles under a view, wrapping at the date line", () => {
    const tiles = map.tilesFor(0, 0, 2, 256, 256);
    assert.deepStrictEqual(tiles.map((tile) => [tile.x, tile.y]), [[1, 1], [2, 1], [1, 2], [2, 2]]);
    assert.deepStrictEqual(tiles.map((tile) => [tile.left, tile.top]), [[-128, -128], [128, -128], [-128, 128], [128, 128]]);
    const across = map.tilesFor(0, 179.9, 3, 512, 256).map((tile) => tile.x);
    assert.ok(across.includes(7) && across.includes(0), String(across));
    // Nothing above the top of the world
    assert.ok(map.tilesFor(85, 0, 1, 256, 1024).every((tile) => tile.y >= 0 && tile.y < 2));
});

// ---- What -----------------------------------------------------------------------

test("streets by importance and zoom", () => {
    assert.ok(map.streetStyle({ kind: "motorway" }, 5));
    assert.strictEqual(map.streetStyle({ kind: "primary" }, 7), null);
    assert.ok(map.streetStyle({ kind: "primary" }, 8));
    assert.strictEqual(map.streetStyle({ kind: "path" }, 12), null);
    assert.strictEqual(map.streetStyle({ kind: "motorway", tunnel: true }, 9), null);
    assert.strictEqual(map.streetStyle({ kind: "rail", rail: true }, 12), null);
    assert.ok(map.streetStyle({ kind: "motorway", link: true }, 9).width < map.streetStyle({ kind: "motorway" }, 9).width);
});

test("country borders solid, state borders dashed, none at sea", () => {
    assert.deepStrictEqual(map.borderStyle({ admin_level: 2 }).dash, []);
    assert.ok(map.borderStyle({ admin_level: "4" }).dash.length);
    assert.strictEqual(map.borderStyle({ admin_level: 2, maritime: true }), null);
    assert.strictEqual(map.borderStyle({ admin_level: 8 }), null);
});

test("place names by importance and zoom", () => {
    assert.ok(map.placeStyle({ kind: "city", name: "Cinder Flats" }, 5));
    assert.strictEqual(map.placeStyle({ kind: "town", name: "Dry Hollow" }, 7), null);
    assert.ok(map.placeStyle({ kind: "town", name: "Dry Hollow" }, 8));
    assert.strictEqual(map.placeStyle({ kind: "city", name: " " }, 8), null);
    assert.strictEqual(map.placeStyle({ kind: "farm", name: "Farm" }, 12), null);
});

test("labels never overlap or repeat; the most important are kept", () => {
    const box = (x, y) => ({ x, y, width: 50, height: 12 });
    const labels = [
        { text: "Small Town", rank: 3, population: 900, box: box(10, 10) },
        { text: "Big City", rank: 2, population: 90000, box: box(30, 12) },
        { text: "Far Town", rank: 3, population: 500, box: box(200, 10) },
        { text: "Far Town", rank: 3, population: 500, box: box(201, 11) },
    ];
    assert.deepStrictEqual(map.placeLabels(labels).map((label) => label.text), ["Big City", "Far Town"]);
    assert.ok(map.insideView(box(0, 0), 50, 12));
    assert.ok(!map.insideView(box(-1, 0), 300, 300));
    assert.ok(!map.insideView(box(260, 0), 300, 300));
});

test("drawing a tile touches the canvas and names the town", () => {
    const calls = [];
    const context = new Proxy({}, {
        get: (target, name) => {
            if (name === "measureText") return (text) => ({ width: text.length * 6 });
            if (name in target) return target[name];
            return (...args) => calls.push([name, ...args]);
        },
        set: (target, name, value) => {
            target[name] = value;
            return true;
        },
    });
    const data = mvt.decode(fixture.sampleTile(), map.LAYERS);
    const colors = { land: "#000", water: "#00f", road: "#f80", border: "#888", label: "#fff", halo: "#000", marker: "#f00" };
    const named = map.draw(context, [{ left: 0, top: 0, data }], { width: 256, height: 256, zoom: 8, colors, font: "monospace" });
    assert.strictEqual(named, 1);
    assert.ok(calls.some(([name, text]) => name === "fillText" && text === "Cinder Flats"));
    assert.ok(calls.some(([name]) => name === "fill"));
    assert.ok(calls.some(([name]) => name === "stroke"));
});
