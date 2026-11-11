// Tests for web/clock.js. Run with: TZ=UTC node --test tests/clock.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const clock = require("../web/clock.js");

const afternoon = new Date("2026-11-08T13:05:00Z");
const justAfterMidnight = new Date("2026-11-08T00:05:00Z");

// A stand-in for localStorage
function memoryStorage(initial = {}) {
    const data = { ...initial };
    return {
        getItem: (key) => (key in data ? data[key] : null),
        setItem: (key, value) => { data[key] = String(value); },
        removeItem: (key) => { delete data[key]; },
        data,
    };
}
const blockedStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
    removeItem() { throw new Error("blocked"); },
};
const server = (value, toggle) => ({ ui: { clock: value, clock_toggle: toggle } });

test("the server setting decides when nothing else does", () => {
    assert.equal(clock.choose({}, "", memoryStorage()).clock, "auto");
    assert.equal(clock.choose(server("24"), "", memoryStorage()).clock, "24");
    assert.equal(clock.choose(server(" 12H "), "", memoryStorage()).clock, "12");
    assert.equal(clock.choose(server("military"), "", memoryStorage()).clock, "auto");
});

test("a choice saved in this browser wins over the server", () => {
    const storage = memoryStorage({ [clock.STORAGE_KEY]: "24" });
    assert.equal(clock.choose(server("12"), "", storage).clock, "24");
});

test("the address wins over everything", () => {
    const storage = memoryStorage({ [clock.STORAGE_KEY]: "24" });
    assert.equal(clock.choose(server("24"), "?clock=12", storage).clock, "12");
    assert.equal(clock.choose(server("24"), "?clock=auto", storage).clock, "auto");
    assert.equal(clock.choose(server("12"), "?clock=25", memoryStorage()).clock, "12");
});

test("a saved choice is ignored when the server hides the checkbox", () => {
    const storage = memoryStorage({ [clock.STORAGE_KEY]: "24" });
    assert.equal(clock.choose(server("12", false), "", storage).clock, "12");
    assert.equal(clock.toggleAllowed(server("12", false)), false);
    assert.equal(clock.toggleAllowed({}), true);
});

test("only 12 or 24 is read back from storage, and blocked storage is harmless", () => {
    assert.equal(clock.readSaved(memoryStorage({ [clock.STORAGE_KEY]: "auto" })), null);
    assert.equal(clock.readSaved(memoryStorage({ [clock.STORAGE_KEY]: "<b>" })), null);
    assert.equal(clock.readSaved(blockedStorage), null);
    assert.equal(clock.writeSaved("24", blockedStorage), false);

    const storage = memoryStorage();
    assert.equal(clock.writeSaved("12", storage), true);
    assert.equal(storage.data[clock.STORAGE_KEY], "12");
    clock.writeSaved(null, storage);
    assert.equal(clock.STORAGE_KEY in storage.data, false);
});

test("auto means whatever the browser's language uses", () => {
    assert.equal(clock.browserDefault("en-US"), "12");
    assert.equal(clock.browserDefault("en-GB"), "24");
    assert.equal(clock.effective("auto", "en-GB"), "24");
    assert.equal(clock.effective("12", "en-GB"), "12");
});

test("12-hour times, even where the language uses 24-hour", () => {
    assert.match(clock.time(afternoon, "12", "en-GB"), /^1:05\s?pm$/i);
    assert.match(clock.time(afternoon, "12", "en-US"), /^1:05\sPM$/);
    assert.match(clock.time(justAfterMidnight, "12", "en-US"), /^12:05\sAM$/);
});

test("24-hour times, even where the language uses 12-hour", () => {
    assert.equal(clock.time(afternoon, "24", "en-US"), "13:05");
    assert.equal(clock.time(justAfterMidnight, "24", "en-US"), "00:05");
    assert.equal(clock.time(justAfterMidnight, "24", "en-GB"), "00:05");
    assert.match(clock.dateTime(new Date("2026-11-08T04:02:00Z"), "24", "en-GB"), /^8 Nov,? 04:02$/);
});

test("auto follows the language", () => {
    assert.match(clock.time(afternoon, "auto", "en-US"), /^1:05\sPM$/);
    assert.equal(clock.time(afternoon, "auto", "en-GB"), "13:05");
});

test("dates with times follow the clock too", () => {
    assert.match(clock.dateTime(afternoon, "24", "en-US"), /^Nov 8, 13:05$/);
    assert.match(clock.dateTime(afternoon, "12", "en-US"), /^Nov 8, 1:05\sPM$/);
});
