// Builds small made-up vector tiles (Mapbox Vector Tile protobuf) for tests: the map's decoder
// (tests/map.test.js) and the browser check (check-themes.js, next to it), with no tile server.
"use strict";

const encoder = new TextEncoder();

function varint(value) {
    const bytes = [];
    let rest = value;
    while (rest >= 128) {
        bytes.push((rest % 128) | 128);
        rest = Math.floor(rest / 128);
    }
    bytes.push(rest);
    return bytes;
}

const zigzag = (value) => (value < 0 ? -2 * value - 1 : 2 * value);
const key = (field, type) => varint(field * 8 + type);
const bytesField = (field, bytes) => [...key(field, 2), ...varint(bytes.length), ...bytes];
const textField = (field, text) => bytesField(field, [...encoder.encode(text)]);
const packed = (field, values) => bytesField(field, values.flatMap(varint));
const command = (id, count) => (id & 7) | (count << 3);

const TYPES = { point: 1, line: 2, polygon: 3 };

// parts: lists of [x, y]; polygon rings are given without repeating the first point
function geometry(type, parts) {
    const commands = [];
    let x = 0;
    let y = 0;
    const move = ([px, py]) => {
        commands.push(zigzag(px - x), zigzag(py - y));
        x = px;
        y = py;
    };
    if (type === "point") {
        const points = parts.flat();
        commands.push(command(1, points.length));
        points.forEach(move);
        return commands;
    }
    for (const part of parts) {
        commands.push(command(1, 1));
        move(part[0]);
        commands.push(command(2, part.length - 1));
        part.slice(1).forEach(move);
        if (type === "polygon") commands.push(command(7, 1));
    }
    return commands;
}

function value(item) {
    if (typeof item === "string") return textField(1, item);
    if (typeof item === "boolean") return [...key(7, 0), ...varint(item ? 1 : 0)];
    if (Number.isInteger(item) && item >= 0) return [...key(5, 0), ...varint(item)];
    if (Number.isInteger(item)) return [...key(6, 0), ...varint(zigzag(item))];
    const bytes = new Uint8Array(8);
    new DataView(bytes.buffer).setFloat64(0, item, true);
    return [...key(3, 1), ...bytes];
}

// layers: { name: { extent, features: [{ type, properties, geometry: parts }] } }
function encodeTile(layers) {
    const tile = [];
    for (const [name, layer] of Object.entries(layers)) {
        const keys = [];
        const values = [];
        const body = [...key(15, 0), ...varint(2), ...textField(1, name)];
        for (const feature of layer.features) {
            const tags = [];
            for (const [property, item] of Object.entries(feature.properties || {})) {
                if (!keys.includes(property)) keys.push(property);
                const encoded = JSON.stringify(value(item));
                let index = values.findIndex((other) => JSON.stringify(other) === encoded);
                if (index < 0) {
                    values.push(value(item));
                    index = values.length - 1;
                }
                tags.push(keys.indexOf(property), index);
            }
            body.push(...bytesField(2, [
                ...packed(2, tags),
                ...key(3, 0), ...varint(TYPES[feature.type]),
                ...packed(4, geometry(feature.type, feature.geometry)),
            ]));
        }
        keys.forEach((name) => body.push(...textField(3, name)));
        values.forEach((encoded) => body.push(...bytesField(4, encoded)));
        body.push(...key(5, 0), ...varint(layer.extent || 4096));
        tile.push(...bytesField(3, body));
    }
    return new Uint8Array(tile);
}

// A tile of the made-up place used in tests: a lake, a motorway, a border, and a town
function sampleLayers() {
    return {
        water_polygons: { extent: 4096, features: [
            { type: "polygon", properties: { kind: "water" }, geometry: [[[100, 100], [900, 100], [900, 900], [100, 900]]] },
        ] },
        streets: { extent: 2048, features: [
            { type: "line", properties: { kind: "motorway", bridge: false }, geometry: [[[0, 1024], [2048, 1100]]] },
            { type: "line", properties: { kind: "path" }, geometry: [[[0, 0], [10, 10]]] },
        ] },
        boundaries: { extent: 4096, features: [
            { type: "line", properties: { admin_level: 2, maritime: false }, geometry: [[[2048, 0], [2048, 4096]]] },
        ] },
        place_labels: { extent: 4096, features: [
            { type: "point", properties: { kind: "city", name: "Cinder Flats", population: 5200 }, geometry: [[[3000, 3000]]] },
        ] },
        buildings: { extent: 4096, features: [
            { type: "polygon", properties: {}, geometry: [[[1, 1], [2, 1], [2, 2]]] },
        ] },
    };
}

function sampleTile() {
    return encodeTile(sampleLayers());
}

module.exports = { encodeTile, sampleLayers, sampleTile, varint, zigzag };
