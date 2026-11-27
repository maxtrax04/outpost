// Tests for web/hourly.js. Run with: TZ=UTC node --test tests/hourly.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const hourly = require("../web/hourly.js");

const NOW = Date.parse("2026-07-15T14:20:00Z");
const hour = (time, extra = {}) => ({ time, temperature: 72, condition: "Clear", icon: "sunny",
    precipitation_chance: 10, wind_speed: 5, wind_direction: 180, ...extra });

test("only hours that haven't ended, in order, at most 12", () => {
    const list = [];
    for (let offset = 20; offset >= -3; offset--) {
        list.push(hour(new Date(Date.parse("2026-07-15T14:00:00Z") + offset * 3600000).toISOString()));
    }
    const upcoming = hourly.upcoming(list, NOW);
    assert.equal(upcoming.length, hourly.SHOWN);
    assert.equal(new Date(upcoming[0].start).toISOString(), "2026-07-15T14:00:00.000Z");
    assert.equal(new Date(upcoming[11].start).toISOString(), "2026-07-16T01:00:00.000Z");
    assert.deepEqual(hourly.upcoming(null, NOW), []);
    // A 3-hour step (OpenWeatherMap's free plan) stays until its end
    const step = { time: "2026-07-15T12:00:00Z", end: "2026-07-15T15:00:00Z" };
    assert.equal(hourly.upcoming([step], NOW).length, 1);
    assert.equal(hourly.upcoming([{ time: step.time, end: "soon" }], NOW).length, 0);
    assert.deepEqual(hourly.upcoming([{ time: "soon" }, null, {}], NOW), []);
});

test("the hour under way is Now, the rest by the clock in the location's zone", () => {
    const [now, later] = hourly.upcoming([hour("2026-07-15T14:00:00Z"), hour("2026-07-15T15:00:00Z")], NOW);
    assert.equal(hourly.cellData(now, NOW).time, "Now");
    assert.equal(hourly.cellData(now, NOW).now, true);
    assert.equal(hourly.cellData(later, NOW, "12", "UTC", "en-US").time, "3 PM");
    assert.equal(hourly.cellData(later, NOW, "24", "UTC", "en-US").time, "15:00");
    assert.equal(hourly.cellData(later, NOW, "12", "America/Chicago", "en-US").time, "10 AM");
});

test("readings, and dashes when missing", () => {
    const [item] = hourly.upcoming([hour("2026-07-15T15:00:00Z", { temperature: 21, precipitation_chance: null,
        icon: 3, condition: "" })], NOW);
    assert.deepEqual(hourly.cellData(item, NOW, "12", "UTC", "en-US"), {
        time: "3 PM", now: false, icon: "unknown", condition: "Unknown", temperature: "21°", rain: "--",
        rainMissing: true,
    });
    const [rainy] = hourly.upcoming([hour("2026-07-15T15:00:00Z", { precipitation_chance: 60 })], NOW);
    assert.equal(hourly.cellData(rainy, NOW).rain, "60%");
});

test("OUTPOST_HOURLY=false turns it off", () => {
    assert.equal(hourly.enabled({}), true);
    assert.equal(hourly.enabled({ ui: { hourly: true } }), true);
    assert.equal(hourly.enabled({ ui: { hourly: false } }), false);
    assert.equal(hourly.enabled(null), true);
});
