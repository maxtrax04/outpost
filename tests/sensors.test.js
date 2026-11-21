// Tests for web/sensors.js. Run with: node --test tests/sensors.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const sensors = require("../web/sensors.js");

test("values with their units", () => {
    assert.equal(sensors.valueText({ text: "21.5", unit: "°C", missing: false }), "21.5°C");
    assert.equal(sensors.valueText({ text: "45", unit: "%", missing: false }), "45%");
    assert.equal(sensors.valueText({ text: "1.2", unit: "kW", missing: false }), "1.2 kW");
    assert.equal(sensors.valueText({ text: "Open", unit: "", missing: false }), "Open");
});

test("missing readings show a dash", () => {
    for (const sensor of [null, {}, { text: "", missing: false }, { text: "21", missing: true }, { text: 21 }]) {
        assert.equal(sensors.valueText(sensor), "--");
    }
});

test("tiles are marked for themes", () => {
    assert.deepEqual(sensors.tileData({ label: "Front door", kind: "binary", value: true, text: "Open",
                                        unit: "", device_class: "door", missing: false }), {
        label: "Front door", value: "Open", kind: "binary", deviceClass: "door", state: "on", missing: false,
    });
    const missing = sensors.tileData({ label: "Shed", kind: "number", value: null, text: "", missing: true });
    assert.equal(missing.value, "--");
    assert.equal(missing.missing, true);
    assert.equal(missing.state, "");
});

test("odd readings are made safe", () => {
    const odd = sensors.tileData({ label: 7, kind: "<script>", device_class: "Bad Class!", text: "x", missing: false });
    assert.equal(odd.label, "Sensor");
    assert.equal(odd.kind, "text");
    assert.equal(odd.deviceClass, "");
    // Missing unless the server says it is not
    assert.equal(sensors.tileData({ text: "5" }).missing, true);
});

test("an answer gives at most 24 tiles, and nothing from anything else", () => {
    assert.deepEqual(sensors.readings(null), []);
    assert.deepEqual(sensors.readings({ sensors: "no" }), []);
    const many = { sensors: Array.from({ length: 30 }, (_, n) => ({ label: `S${n}`, text: "1", missing: false })) };
    assert.equal(sensors.readings(many).length, 24);
});

test("power tiles: the grid's direction and the battery's charge", () => {
    assert.deepEqual(sensors.powerData({ role: "grid", label: "Grid", text: "1.2", unit: "kW", value: 1.2,
                                         direction: "import", missing: false }), {
        role: "grid", label: "Grid", value: "1.2 kW", missing: false, direction: "import", note: "Importing", fraction: null,
    });
    const exporting = sensors.powerData({ role: "grid", text: "800", unit: "W", direction: "export", missing: false });
    assert.equal(exporting.note, "Exporting");
    assert.equal(exporting.label, "Grid");
    const battery = sensors.powerData({ role: "battery", label: "Battery", text: "85", unit: "%", fraction: 0.85, missing: false });
    assert.equal(battery.value, "85%");
    assert.equal(battery.fraction, 0.85);
    assert.equal(sensors.powerData({ role: "battery", text: "85", unit: "%", fraction: 7, missing: false }).fraction, 1);
});

test("missing or odd power readings", () => {
    const missing = sensors.powerData({ role: "grid", label: "Grid", text: "", direction: "import", missing: true });
    assert.equal(missing.value, "--");
    assert.equal(missing.direction, "");
    assert.equal(missing.note, "");
    assert.equal(sensors.powerData({ role: "battery", text: "85", fraction: 0.85, missing: true }).fraction, null);
    assert.equal(sensors.powerData({ role: "grid", text: "1", direction: "<b>", missing: false }).direction, "");
    for (const odd of [null, "x", {}, { role: "car" }, { role: "__proto__" }]) {
        assert.equal(sensors.powerData(odd), null);
    }
});

test("power roles are shown once each, in their order", () => {
    assert.deepEqual(sensors.powerReadings(null), []);
    assert.deepEqual(sensors.powerReadings({ sensors: [] }), []);
    const answer = { power: [
        { role: "battery", text: "50", missing: false }, { role: "home", text: "1", missing: false },
        { role: "home", text: "2", missing: false }, { role: "car", text: "3", missing: false },
    ] };
    assert.deepEqual(sensors.powerReadings(answer).map((data) => [data.role, data.value]),
                     [["home", "1"], ["battery", "50"]]);
});
