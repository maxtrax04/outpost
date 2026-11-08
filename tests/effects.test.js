// Tests for web/effects.js. Run with: node --test tests/effects.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const effects = require("../web/effects.js");

function memoryStorage(initial = {}) {
    const data = { ...initial };
    return {
        data,
        getItem: (key) => (key in data ? data[key] : null),
        setItem: (key, value) => { data[key] = String(value); },
        removeItem: (key) => { delete data[key]; },
    };
}

const blockedStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
    removeItem() { throw new Error("blocked"); },
};

const server = (ui) => ({ ui });
const saved = (value) => memoryStorage({ [effects.STORAGE_KEY]: value });

test("full by default", () => {
    assert.equal(effects.choose({}, "", memoryStorage(), false).effects, "full");
    assert.equal(effects.choose(undefined, "", memoryStorage(), false).effects, "full");
});

test("the server can reduce effects for everyone", () => {
    assert.equal(effects.choose(server({ effects: "reduced" }), "", memoryStorage(), false).effects, "reduced");
});

test("a device that asks for reduced motion gets reduced effects", () => {
    assert.equal(effects.choose(server({ effects: "full" }), "", memoryStorage(), true).effects, "reduced");
});

test("the viewer's saved choice wins over the server and the device", () => {
    assert.equal(effects.choose(server({ effects: "reduced" }), "", saved("full"), true).effects, "full");
    assert.equal(effects.choose(server({ effects: "full" }), "", saved("reduced"), false).effects, "reduced");
});

test("the address wins over everything", () => {
    assert.equal(effects.choose(server({}), "?effects=reduced", saved("full"), false).effects, "reduced");
    assert.equal(effects.choose(server({ effects: "reduced" }), "?effects=full", saved("reduced"), true).effects, "full");
});

test("a saved choice is ignored when the server hides the toggle", () => {
    const config = server({ effects: "reduced", effects_toggle: false });
    const choice = effects.choose(config, "", saved("full"), false);
    assert.equal(choice.effects, "reduced");
    assert.equal(choice.saved, null);
    assert.equal(effects.toggleAllowed(config), false);
    assert.equal(effects.toggleAllowed(server({})), true);
    assert.equal(effects.toggleAllowed(undefined), true);
});

test("unknown values are ignored", () => {
    assert.equal(effects.choose(server({ effects: "sparkly" }), "?effects=loud", saved("max"), false).effects, "full");
    assert.equal(effects.valid("reduced"), "reduced");
    assert.equal(effects.valid("REDUCED"), null);
});

test("blocked browser storage never throws", () => {
    assert.equal(effects.readSaved(blockedStorage), null);
    assert.equal(effects.writeSaved("reduced", blockedStorage), false);
    assert.equal(effects.choose(server({}), "", blockedStorage, false).effects, "full");
});

test("saving and forgetting a choice", () => {
    const storage = memoryStorage();
    assert.equal(effects.writeSaved("reduced", storage), true);
    assert.equal(effects.readSaved(storage), "reduced");
    effects.writeSaved(null, storage);
    assert.equal(effects.readSaved(storage), null);
});
