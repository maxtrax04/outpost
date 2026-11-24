// Tests for web/data.js. Run with: node --test tests/data.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const data = require("../web/data.js");

test("unit labels come from the units block", () => {
    const given = { system: "metric", temperature: "°C", speed: "km/h", pressure: "hPa", distance: "km", precipitation: "mm" };
    assert.deepStrictEqual(data.units({ units: given }), given);
});

test("a metric file from before 0.8.0 gets mm for precipitation", () => {
    const old = { system: "metric", temperature: "°C", speed: "km/h", pressure: "hPa", distance: "km" };
    assert.strictEqual(data.units({ units: old }).precipitation, "mm");
    assert.strictEqual(data.units({}).precipitation, "in");
});

test("a forecast day's amount is shown only when some is expected", () => {
    assert.strictEqual(data.amountText(0.3, data.units({})), "0.30 in");
    assert.strictEqual(data.amountText(7.6, data.units({ units: { system: "metric" } })), "7.6 mm");
    for (const value of [0, null, undefined, "0.3", NaN, -1]) {
        assert.strictEqual(data.amountText(value, data.units({})), "");
    }
    assert.strictEqual(data.amountText(0.05), "0.05 in");
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

// A stand-in for window.fetch: answers by address, records what was asked
function fakeFetch(answers) {
    const asked = [];
    const fetchFn = async (url) => {
        asked.push(url);
        const answer = answers[url.split("?")[0]];
        if (answer instanceof Error) throw answer;
        return { ok: answer === 200, status: answer };
    };
    return { fetchFn, asked };
}

test("the weather is read from the API first", async () => {
    const { fetchFn, asked } = fakeFetch({ "api/weather": 200, "data/weather.json": 200 });
    const response = await data.fetchWeather(fetchFn, 42);
    assert.strictEqual(response.ok, true);
    assert.deepStrictEqual(asked, ["api/weather?cacheBust=42"]);
});

test("without the API, the weather is read from weather.json", async () => {
    for (const api of [404, 502, new TypeError("Failed to fetch")]) {
        const { fetchFn, asked } = fakeFetch({ "api/weather": api, "data/weather.json": 200 });
        const response = await data.fetchWeather(fetchFn, 7);
        assert.strictEqual(response.ok, true);
        assert.deepStrictEqual(asked, ["api/weather?cacheBust=7", "data/weather.json?cacheBust=7"]);
    }
});

test("when neither works, the last error is thrown", async () => {
    const { fetchFn } = fakeFetch({ "api/weather": 502, "data/weather.json": 404 });
    await assert.rejects(data.fetchWeather(fetchFn, 1), /HTTP 404/);
});

test("the weather addresses are relative, for a path prefix", () => {
    for (const url of data.WEATHER_URLS) assert.ok(!url.startsWith("/"), url);
});

test("another place is asked of the API alone, never weather.json", async () => {
    const asked = [];
    const fetchFn = async (url) => {
        asked.push(url);
        return { ok: true, status: 200 };
    };
    await data.fetchWeather(fetchFn, 5, "api/weather?lat=1&lon=2&name=Here");
    assert.deepStrictEqual(asked, ["api/weather?lat=1&lon=2&name=Here&cacheBust=5"]);
});

test("a refused place gives the API's own message", async () => {
    const asked = [];
    const refused = async (url) => {
        asked.push(url);
        return { ok: false, status: 429, json: async () => ({ error: "location_limit", message: "Too many places" }) };
    };
    await assert.rejects(data.fetchWeather(refused, 5, "api/weather?lat=1&lon=2"),
        (error) => error.status === 429 && error.apiMessage === "Too many places" && error.message === "Too many places");
    assert.strictEqual(asked.length, 1);

    // nginx's own pages are not JSON
    const page = async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError("not JSON"); } });
    await assert.rejects(data.fetchWeather(page, 5, "api/weather?lat=1&lon=2"),
        (error) => error.status === 502 && error.apiMessage === "" && error.message === "HTTP 502");
});
