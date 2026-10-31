// Tests for web/dim.js. Run with: node --test tests/dim.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const dim = require("../web/dim.js");

const at = (iso) => new Date(iso);
const close = (actual, expected, tolerance, message) =>
    assert.ok(Math.abs(actual - expected) <= tolerance, `${message || ""} expected ${expected} +/- ${tolerance}, got ${actual}`);

test("solar elevation matches reference values (New York, 2024-06-20)", () => {
    const [lat, lon] = [40.7128, -74.0060];
    // Official sunrise/sunset is when the sun's edge touches the horizon (about -0.83 degrees)
    close(dim.solarElevation(at("2024-06-20T09:25:00Z"), lat, lon), -0.83, 1.0, "sunrise");
    close(dim.solarElevation(at("2024-06-21T00:31:00Z"), lat, lon), -0.83, 1.0, "sunset");
    close(dim.solarElevation(at("2024-06-20T16:57:00Z"), lat, lon), 72.7, 0.7, "solar noon");
});

test("solar elevation is sane on the equinox and in the southern hemisphere", () => {
    assert.ok(dim.solarElevation(at("2024-03-20T12:00:00Z"), 0, 0) > 85);
    assert.ok(dim.solarElevation(at("2024-12-21T01:00:00Z"), -33.87, 151.21) > 70);
    assert.ok(dim.solarElevation(at("2024-12-20T14:00:00Z"), -33.87, 151.21) < 0);
});

const sunConfig = { latitude: 10, longitude: 20, dim: { enabled: true, level: 0.35, mode: "sun" } };

test("sun mode is bright at midday and at the night level at midnight", () => {
    // Longitude 20 east: local solar noon is about 10:40 UTC
    close(dim.brightness(sunConfig, at("2026-07-15T10:40:00Z")), 1, 1e-9, "noon");
    close(dim.brightness(sunConfig, at("2026-07-14T22:40:00Z")), 0.35, 1e-9, "midnight");
});

test("sun mode fades smoothly through dusk", () => {
    let previous = 1;
    let sawMiddle = false;
    for (let minutes = 0; minutes <= 180; minutes += 5) {
        const value = dim.brightness(sunConfig, new Date(Date.parse("2026-07-15T15:30:00Z") + minutes * 60000));
        assert.ok(value <= previous + 1e-9, "brightness must not increase after sunset");
        if (value > 0.4 && value < 0.95) sawMiddle = true;
        previous = value;
    }
    assert.ok(sawMiddle, "should pass through intermediate brightness");
    close(previous, 0.35, 1e-9, "ends at night level");
});

test("dimming can be disabled", () => {
    assert.equal(dim.brightness({ dim: { enabled: false } }, at("2026-07-14T22:40:00Z")), 1);
});

test("sun mode without coordinates never goes dark", () => {
    assert.equal(dim.brightness({ dim: { mode: "sun" } }, at("2026-07-14T22:40:00Z")), 1);
    assert.equal(dim.brightness({}, new Date()), 1);
});

test("the night level is clamped to 0.05", () => {
    const config = { latitude: 10, longitude: 20, dim: { level: -3 } };
    close(dim.brightness(config, at("2026-07-14T22:40:00Z")), 0.05, 1e-9);
});

// Schedule mode uses the machine's local time, so build dates in local time
const scheduleConfig = (extra = {}) => ({ dim: { mode: "schedule", start: "22:00", end: "06:00", level: 0.2, ...extra } });
const local = (h, m) => new Date(2026, 6, 15, h, m, 0);

test("schedule mode across midnight", () => {
    const config = scheduleConfig();
    assert.equal(dim.brightness(config, local(21, 59)), 1);
    close(dim.brightness(config, local(22, 15)), 0.6, 0.01, "half faded in");
    close(dim.brightness(config, local(23, 0)), 0.2, 1e-9);
    close(dim.brightness(config, local(3, 0)), 0.2, 1e-9);
    close(dim.brightness(config, local(6, 15)), 0.6, 0.01, "half faded out");
    assert.equal(dim.brightness(config, local(6, 30)), 1);
    assert.equal(dim.brightness(config, local(12, 0)), 1);
});

test("schedule mode within one day", () => {
    const config = scheduleConfig({ start: "13:00", end: "15:00", level: 0.5 });
    close(dim.brightness(config, local(14, 0)), 0.5, 1e-9);
    assert.equal(dim.brightness(config, local(16, 0)), 1);
});

test("schedule mode ignores invalid times", () => {
    assert.equal(dim.brightness(scheduleConfig({ start: "25:99" }), local(23, 0)), 1);
    assert.equal(dim.brightness(scheduleConfig({ start: "22:00", end: "22:00" }), local(23, 0)), 1);
});

test("time parsing", () => {
    assert.equal(dim.parseTime("22:30"), 1350);
    assert.equal(dim.parseTime("6:05"), 365);
    assert.equal(dim.parseTime("24:00"), null);
    assert.equal(dim.parseTime("nope"), null);
});

// ---- Sunrise and sunset ----------------------------------------------------
// These tests build the local day in the machine's time zone. CI runs with TZ=UTC,
// and London is used because it sits on the UTC meridian, so its sun times fall on one UTC day.
const minutesBetween = (a, b) => Math.abs(a.getTime() - b.getTime()) / 60000;

test("sunrise and sunset match published times (London, 2024-06-20)", { skip: process.env.TZ !== "UTC" && "needs TZ=UTC" }, () => {
    const times = dim.sunTimes(new Date(Date.UTC(2024, 5, 20, 12, 0)), 51.5074, -0.1278);
    assert.equal(times.polar, null);
    // Published: sunrise 04:43 BST (03:43 UTC), sunset 21:21 BST (20:21 UTC)
    assert.ok(minutesBetween(times.sunrise, new Date(Date.UTC(2024, 5, 20, 3, 43))) < 4, `sunrise ${times.sunrise.toISOString()}`);
    assert.ok(minutesBetween(times.sunset, new Date(Date.UTC(2024, 5, 20, 20, 21))) < 4, `sunset ${times.sunset.toISOString()}`);
});

test("sunset comes after sunrise and day length is plausible", () => {
    const times = dim.sunTimes(new Date(2026, 2, 20, 12, 0), 10, 20);
    assert.ok(times.sunset > times.sunrise);
    const hours = (times.sunset - times.sunrise) / 3600000;
    assert.ok(hours > 11.5 && hours < 12.8, `near the equinox the day is about 12 hours, got ${hours.toFixed(2)}`);
});

test("midnight sun and polar night", () => {
    // Tromso, Norway
    assert.equal(dim.sunTimes(new Date(2026, 5, 20, 12, 0), 69.65, 18.96).polar, "day");
    assert.equal(dim.sunTimes(new Date(2026, 11, 20, 12, 0), 69.65, 18.96).polar, "night");
});

test("sun times need coordinates", () => {
    assert.equal(dim.sunTimes(new Date(), NaN, 20), null);
    assert.equal(dim.sunTimes(new Date(), 10, undefined), null);
});

test("sunrise and sunset agree with the dimming math", () => {
    const times = dim.sunTimes(new Date(2026, 6, 15, 12, 0), 10, 20);
    // At sunrise and sunset the sun's edge is at the horizon (about -0.83 degrees)
    assert.ok(Math.abs(dim.solarElevation(times.sunrise, 10, 20) + 0.833) < 0.1);
    assert.ok(Math.abs(dim.solarElevation(times.sunset, 10, 20) + 0.833) < 0.1);
});

// ---- coordinates() ---------------------------------------------------------
test("coordinates accepts numbers and numeric strings", () => {
    assert.deepEqual(dim.coordinates({ latitude: 10, longitude: -20 }), { latitude: 10, longitude: -20 });
    assert.deepEqual(dim.coordinates({ latitude: "10.5", longitude: "-20.25" }), { latitude: 10.5, longitude: -20.25 });
    assert.deepEqual(dim.coordinates({ latitude: 0, longitude: 0 }), { latitude: 0, longitude: 0 });
});

test("coordinates rejects missing, empty, and invalid values instead of treating them as 0", () => {
    const bad = [{}, null, undefined, { latitude: null, longitude: null }, { latitude: "", longitude: "" },
        { latitude: "  ", longitude: " " }, { latitude: "abc", longitude: "def" }, { latitude: 10 },
        { latitude: 95, longitude: 10 }, { latitude: 10, longitude: 200 }];
    for (const config of bad) {
        assert.equal(dim.coordinates(config), null, JSON.stringify(config));
    }
});

test("sun-based dimming does not treat empty coordinates as the equator", () => {
    // At 22:40 UTC it is night at longitude 20 east, but (0, 0) would be mid-evening
    const night = at("2026-07-14T22:40:00Z");
    assert.equal(dim.brightness({ latitude: null, longitude: null, dim: { mode: "sun", level: 0.2 } }, night), 1);
    assert.equal(dim.brightness({ latitude: "", longitude: "", dim: { mode: "sun", level: 0.2 } }, night), 1);
});
