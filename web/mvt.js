// Decodes a Mapbox Vector Tile (the protobuf format of OpenStreetMap's vector tiles), for the map
// panel (map.js, docs/map-design.md). Only what drawing needs: each wanted layer's features, with
// their properties and geometry in tile units (0..extent). Spec: github.com/mapbox/vector-tile-spec
// Kept apart from map.js so it can be tested without a page.

(function (root) {
    "use strict";

    const GEOMETRY = { 1: "point", 2: "line", 3: "polygon" };
    const decoder = typeof TextDecoder !== "undefined" ? new TextDecoder("utf-8") : null;

    // A minimal protobuf reader over a Uint8Array
    class Reader {
        constructor(bytes, start = 0, end = bytes.length) {
            this.bytes = bytes;
            this.pos = start;
            this.end = end;
        }

        // Varints up to 2^53 (beyond 32 bits, so no bitwise operators)
        varint() {
            let result = 0;
            let scale = 1;
            for (let shift = 0; shift < 64; shift += 7) {
                if (this.pos >= this.end) throw new Error("truncated varint");
                const byte = this.bytes[this.pos++];
                result += (byte & 0x7f) * scale;
                if (byte < 0x80) return result;
                scale *= 128;
            }
            throw new Error("varint too long");
        }

        // { field, type } of the next key, or null at the end
        key() {
            if (this.pos >= this.end) return null;
            const value = this.varint();
            return { field: Math.floor(value / 8), type: value % 8 };
        }

        // The [start, end) of a length-delimited field
        span() {
            const length = this.varint();
            const start = this.pos;
            this.pos += length;
            if (this.pos > this.end) throw new Error("truncated field");
            return [start, this.pos];
        }

        skip(type) {
            if (type === 0) this.varint();
            else if (type === 1) this.pos += 8;
            else if (type === 2) this.span();
            else if (type === 5) this.pos += 4;
            else throw new Error(`unsupported wire type ${type}`);
            if (this.pos > this.end) throw new Error("truncated field");
        }

        // A packed repeated varint field
        packed() {
            const [start, end] = this.span();
            const inner = new Reader(this.bytes, start, end);
            const values = [];
            while (inner.pos < end) values.push(inner.varint());
            return values;
        }

        text() {
            const [start, end] = this.span();
            const slice = this.bytes.subarray(start, end);
            if (decoder) return decoder.decode(slice);
            let result = "";
            for (const byte of slice) result += String.fromCharCode(byte);
            return result;
        }
    }

    const zigzag = (value) => (value % 2 === 1 ? -(value + 1) / 2 : value / 2);

    function readValue(reader, start, end) {
        const inner = new Reader(reader.bytes, start, end);
        const view = new DataView(reader.bytes.buffer, reader.bytes.byteOffset, reader.bytes.byteLength);
        let value = null;
        for (let key = inner.key(); key; key = inner.key()) {
            if (key.field === 1 && key.type === 2) value = inner.text();
            else if (key.field === 2 && key.type === 5) { value = view.getFloat32(inner.pos, true); inner.pos += 4; }
            else if (key.field === 3 && key.type === 1) { value = view.getFloat64(inner.pos, true); inner.pos += 8; }
            else if ((key.field === 4 || key.field === 5) && key.type === 0) value = inner.varint();
            else if (key.field === 6 && key.type === 0) value = zigzag(inner.varint());
            else if (key.field === 7 && key.type === 0) value = inner.varint() !== 0;
            else inner.skip(key.type);
        }
        return value;
    }

    // Geometry commands -> a list of parts, each a list of [x, y]: points, lines, or polygon rings
    function decodeGeometry(commands, type) {
        const parts = [];
        let current = null;
        let x = 0;
        let y = 0;
        let index = 0;
        while (index < commands.length) {
            const command = commands[index] & 0x7;
            const count = commands[index] >> 3;
            index += 1;
            if (command === 1 || command === 2) { // MoveTo, LineTo
                for (let n = 0; n < count && index + 1 < commands.length; n += 1) {
                    x += zigzag(commands[index]);
                    y += zigzag(commands[index + 1]);
                    index += 2;
                    if (command === 1) {
                        current = [];
                        parts.push(current);
                    }
                    if (current) current.push([x, y]);
                }
            } else if (command === 7) { // ClosePath
                if (current && current.length) current.push(current[0].slice());
            } else {
                break; // unknown command: stop rather than draw garbage
            }
        }
        // Points: one part per point is wasteful; keep them flat as one part
        if (type === "point") return [parts.flat()];
        return parts;
    }

    function decodeFeature(reader, start, end, keys, values) {
        const inner = new Reader(reader.bytes, start, end);
        let tags = [];
        let type = 0;
        let commands = [];
        for (let key = inner.key(); key; key = inner.key()) {
            if (key.field === 2 && key.type === 2) tags = inner.packed();
            else if (key.field === 3 && key.type === 0) type = inner.varint();
            else if (key.field === 4 && key.type === 2) commands = inner.packed();
            else inner.skip(key.type);
        }
        const properties = {};
        for (let index = 0; index + 1 < tags.length; index += 2) {
            const name = keys[tags[index]];
            if (name !== undefined) properties[name] = values[tags[index + 1]];
        }
        const kind = GEOMETRY[type] || "unknown";
        return { type: kind, properties, geometry: kind === "unknown" ? [] : decodeGeometry(commands, kind) };
    }

    function decodeLayer(reader, start, end, wanted) {
        const inner = new Reader(reader.bytes, start, end);
        let name = "";
        let extent = 4096;
        const keys = [];
        const values = [];
        const features = [];
        for (let key = inner.key(); key; key = inner.key()) {
            if (key.field === 1 && key.type === 2) name = inner.text();
            else if (key.field === 2 && key.type === 2) features.push(inner.span());
            else if (key.field === 3 && key.type === 2) keys.push(inner.text());
            else if (key.field === 4 && key.type === 2) { const [s, e] = inner.span(); values.push(readValue(inner, s, e)); }
            else if (key.field === 5 && key.type === 0) extent = inner.varint();
            else inner.skip(key.type);
            if (name && wanted && !wanted.has(name)) return null; // not wanted: skip the rest
        }
        if (wanted && !wanted.has(name)) return null;
        return { name, extent, features: features.map(([s, e]) => decodeFeature(reader, s, e, keys, values)) };
    }

    // { layerName: { name, extent, features: [{ type, properties, geometry }] } } for the layers in
    // wanted (an array or Set of names; all layers when it is omitted)
    function decode(buffer, wanted) {
        const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        const names = wanted ? new Set(wanted) : null;
        const reader = new Reader(bytes);
        const layers = {};
        for (let key = reader.key(); key; key = reader.key()) {
            if (key.field === 3 && key.type === 2) {
                const [start, end] = reader.span();
                const layer = decodeLayer(reader, start, end, names);
                if (layer) layers[layer.name] = layer;
            } else {
                reader.skip(key.type);
            }
        }
        return layers;
    }

    const api = { decode, decodeGeometry, zigzag };

    root.OutpostMvt = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
