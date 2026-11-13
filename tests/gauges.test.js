// Tests for web/gauges.js. Run with: node --test tests/gauges.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const gauges = require("../web/gauges.js");

// Just enough of the DOM: elements with a style and attributes, found by data-metric
function fakeElement() {
    const props = new Map();
    const attrs = new Set();
    return {
        props, attrs,
        style: {
            setProperty: (name, value) => props.set(name, value),
            removeProperty: (name) => props.delete(name),
        },
        toggleAttribute: (name, on) => (on ? attrs.add(name) : attrs.delete(name)),
    };
}

function fakeDocument(metrics) {
    const elements = Object.fromEntries(metrics.map((name) => [name, fakeElement()]));
    return {
        elements,
        documentElement: fakeElement(),
        querySelectorAll: (selector) => {
            const name = /\[data-metric="([^"]+)"\]/.exec(selector)[1];
            return elements[name] ? [elements[name]] : [];
        },
    };
}

test("readings are scaled to 0..1 and clamped", () => {
    assert.equal(gauges.scale(50, 0, 100), 0.5);
    assert.equal(gauges.scale(29.75, 28.5, 31), 0.5);
    assert.equal(gauges.scale(-40, -20, 120), 0);
    assert.equal(gauges.scale(130, -20, 120), 1);
    assert.equal(gauges.scale("38", 0, 100), 0.38);
});

test("missing or unusable readings give null", () => {
    for (const value of [null, undefined, "", "n/a", NaN, Infinity, true]) {
        assert.equal(gauges.scale(value, 0, 100), null, `for ${String(value)}`);
    }
});

test("current readings go on the page root and on their element", () => {
    const doc = fakeDocument(["humidity", "uv", "wind"]);
    const result = gauges.applyCurrent({ humidity: 38, uv_index: 5.5, wind_speed: null }, doc);

    assert.equal(result.humidity, 0.38);
    assert.equal(doc.documentElement.props.get("--wx-humidity"), "0.380");
    assert.equal(doc.elements.humidity.props.get("--value"), "0.380");
    assert.equal(doc.elements.uv.props.get("--value"), "0.500");
    assert.ok(!doc.elements.humidity.attrs.has("data-missing"));
    assert.ok(doc.elements.humidity.attrs.has("data-gauge"));
    assert.ok(doc.elements.wind.attrs.has("data-gauge"), "a gauge with no value is still a gauge");

    // A missing reading clears the value, so CSS falls back, and marks the element
    assert.ok(!doc.documentElement.props.has("--wx-wind"));
    assert.ok(!doc.elements.wind.props.has("--value"));
    assert.ok(doc.elements.wind.attrs.has("data-missing"));
});

test("a reading that disappears is cleared on the next update", () => {
    const doc = fakeDocument(["humidity"]);
    gauges.applyCurrent({ humidity: 80 }, doc);
    gauges.applyCurrent({}, doc);
    assert.ok(!doc.documentElement.props.has("--wx-humidity"));
    assert.ok(!doc.elements.humidity.props.has("--value"));
    assert.ok(doc.elements.humidity.attrs.has("data-missing"));
});

test("no weather data at all clears everything", () => {
    const doc = fakeDocument(Object.keys(gauges.CURRENT));
    gauges.applyCurrent({ temperature: 70, humidity: 50 }, doc);
    gauges.applyCurrent(undefined, doc);
    assert.equal(doc.documentElement.props.size, 0);
});

test("forecast values go on the card", () => {
    const card = fakeElement();
    gauges.applyForecast(card, { high: 50, low: -20, precipitation_chance: 100, uv_index: null });
    assert.equal(card.props.get("--wx-high"), "0.500");
    assert.equal(card.props.get("--wx-low"), "0.000");
    assert.equal(card.props.get("--wx-rain"), "1.000");
    assert.ok(!card.props.has("--wx-uv"));
});

test("every current reading has an element in index.html, and the docs list it", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "web", "index.html"), "utf8");
    const docs = fs.readFileSync(path.join(__dirname, "..", "docs", "themes.md"), "utf8");
    for (const name of Object.keys(gauges.CURRENT)) {
        assert.match(html, new RegExp(`data-metric="${name}"`), `index.html has no data-metric="${name}"`);
        assert.ok(docs.includes(`\`--wx-${name}\``), `docs/themes.md does not list --wx-${name}`);
    }
    for (const name of Object.keys(gauges.FORECAST)) {
        assert.ok(docs.includes(`\`--wx-${name}\``), `docs/themes.md does not list --wx-${name}`);
    }
});

test("every field read is one the updater writes", () => {
    const updater = fs.readFileSync(path.join(__dirname, "..", "app", "outpost_updater.py"), "utf8")
        + fs.readFileSync(path.join(__dirname, "..", "app", "providers", "openmeteo.py"), "utf8");
    for (const [field] of [...Object.values(gauges.CURRENT), ...Object.values(gauges.FORECAST)]) {
        assert.ok(updater.includes(`"${field}"`), `${field} is not written by the updater`);
    }
});
