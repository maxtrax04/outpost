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

test("an alerts source that may not cover the location is named when it reports none", () => {
    const pirate = { sources: { alerts: { id: "pirateweather", name: "Pirate Weather" } } };
    assert.strictEqual(data.uncertainAlertsSource(pirate), "Pirate Weather");
    assert.strictEqual(data.uncertainAlertsSource({ sources: { alerts: { id: "nws", name: "NWS" } } }), "");
    assert.strictEqual(data.uncertainAlertsSource({ sources: { alerts: null } }), "");
    assert.strictEqual(data.uncertainAlertsSource({}), "");
});

test("the gust line shows gusts stronger than the wind", () => {
    const mph = data.units({});
    assert.strictEqual(data.gustText({ wind_speed: 9, wind_gust: 18 }, mph), "Gusts 18 mph");
    assert.strictEqual(data.gustText({ wind_speed: 20, wind_gust: 31 }, { speed: "km/h" }), "Gusts 31 km/h");
    assert.strictEqual(data.gustText({ wind_speed: null, wind_gust: 12 }, mph), "Gusts 12 mph");
});

test("no gust line without a gust, or when it is no stronger than the wind", () => {
    const mph = data.units({});
    for (const current of [{ wind_speed: 9, wind_gust: null }, { wind_speed: 9 }, { wind_speed: 9, wind_gust: 9 },
        { wind_speed: 9, wind_gust: 5 }, { wind_speed: 9, wind_gust: "18" }, null]) {
        assert.strictEqual(data.gustText(current, mph), "");
    }
});

test("wind direction as one of 8 compass points", () => {
    const cases = [[0, "N"], [22, "N"], [23, "NE"], [90, "E"], [200, "S"], [225, "SW"], [270, "W"], [337, "NW"],
        [338, "N"], [359, "N"], [360, "N"], [-90, "W"]];
    for (const [degrees, point] of cases) {
        assert.strictEqual(data.compass(degrees), point, `${degrees}°`);
    }
    for (const value of [null, undefined, "SW", NaN]) {
        assert.strictEqual(data.compass(value), "");
    }
});

test("the wind reading has its direction, says calm at 0, and shows -- without a speed", () => {
    const mph = data.units({});
    assert.strictEqual(data.windText({ wind_speed: 12, wind_direction: 225 }, mph), "SW 12 mph");
    assert.strictEqual(data.windText({ wind_speed: 19, wind_direction: 90 }, { speed: "km/h" }), "E 19 km/h");
    assert.strictEqual(data.windText({ wind_speed: 12, wind_direction: null }, mph), "12 mph");
    assert.strictEqual(data.windText({ wind_speed: 0, wind_direction: null }, mph), "Calm");
    assert.strictEqual(data.windText({ wind_speed: null, wind_direction: 225 }, mph), "--");
    assert.strictEqual(data.windText(null, mph), "--");
});

test("the dew point line", () => {
    assert.strictEqual(data.dewPointText({ dew_point: 54 }, data.units({})), "Dew point 54°F");
    assert.strictEqual(data.dewPointText({ dew_point: -3 }, { temperature: "°C" }), "Dew point -3°C");
    for (const current of [{ dew_point: null }, {}, { dew_point: "54" }, null]) {
        assert.strictEqual(data.dewPointText(current, data.units({})), "");
    }
});

test("the reading time is given only when the readings are over an hour old", () => {
    const now = Date.parse("2026-11-14T15:00:00Z");
    const weather = (observed) => ({ current: { observed_at: observed } });
    assert.strictEqual(data.oldReadingTime(weather("2026-11-14T14:30:00+00:00"), now), null);
    assert.strictEqual(data.oldReadingTime(weather("2026-11-14T14:00:00+00:00"), now), null);  // exactly an hour
    assert.strictEqual(data.oldReadingTime(weather("2026-11-14T13:40:00+00:00"), now).toISOString(),
        "2026-11-14T13:40:00.000Z");
    for (const value of [weather(null), weather("soon"), { current: {} }, {}, null]) {
        assert.strictEqual(data.oldReadingTime(value, now), null);
    }
});
