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
