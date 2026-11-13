// Tests for web/data.js. Run with: node --test tests/data.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const data = require("../web/data.js");

test("unit labels come from the units block", () => {
    const units = data.units({ units: { system: "metric", temperature: "°C", speed: "km/h", pressure: "hPa", distance: "km" } });
    assert.deepStrictEqual(units, { system: "metric", temperature: "°C", speed: "km/h", pressure: "hPa", distance: "km" });
});

test("missing or unusable unit labels fall back to imperial", () => {
    assert.deepStrictEqual(data.units({}), data.DEFAULT_UNITS);
    assert.deepStrictEqual(data.units(null), data.DEFAULT_UNITS);
    assert.deepStrictEqual(data.units({ units: "imperial" }), data.DEFAULT_UNITS);
    assert.strictEqual(data.units({ units: { temperature: "", speed: 5 } }).speed, "mph");
});

test("the source line credits each source once", () => {
    const nws = { id: "nws", name: "National Weather Service (weather.gov)" };
    const fill = { id: "openmeteo", name: "Open-Meteo.com", fields: ["current.uv_index"] };
    assert.strictEqual(data.sourceText({ sources: { weather: nws, alerts: nws, fill: null } }),
        "National Weather Service (weather.gov)");
    assert.strictEqual(data.sourceText({ sources: { weather: nws, alerts: nws, fill } }),
        "National Weather Service (weather.gov); Open-Meteo.com");
    assert.strictEqual(data.sourceText({ sources: { weather: { id: "a", name: "A" }, alerts: { id: "b", name: "B" } } }), "A; B");
});

test("the source line is a dash when nothing is known", () => {
    assert.strictEqual(data.sourceText({ sources: { weather: null, alerts: null, fill: null } }), "--");
    assert.strictEqual(data.sourceText({}), "--");
});

test("alerts are supported only when an alerts source is named", () => {
    assert.strictEqual(data.alertsSupported({ sources: { alerts: { id: "nws", name: "NWS" } } }), true);
    assert.strictEqual(data.alertsSupported({ sources: { alerts: null } }), false);
    assert.strictEqual(data.alertsSupported({}), false);
});

test("the dashboard reads the format the updater writes", () => {
    const fs = require("node:fs");
    const updater = fs.readFileSync(require.resolve("../app/outpost_updater.py"), "utf8");
    assert.match(updater, new RegExp(`^SCHEMA_VERSION = ${data.SCHEMA_VERSION}$`, "m"));
});
