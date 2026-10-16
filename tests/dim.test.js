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
