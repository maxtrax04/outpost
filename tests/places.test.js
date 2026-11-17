// Tests for web/places.js. Run with: node --test tests/places.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const places = require("../web/places.js");

class Storage {
    constructor() { this.items = {}; }
    getItem(name) { return name in this.items ? this.items[name] : null; }
    setItem(name, value) { this.items[name] = String(value); }
    removeItem(name) { delete this.items[name]; }
}

class BlockedStorage {
    getItem() { throw new Error("blocked"); }
    setItem() { throw new Error("blocked"); }
    removeItem() { throw new Error("blocked"); }
}

const CINDER = { name: "Cinder Flats, North Province", latitude: 41.5, longitude: -101.25 };
const HOLLOW = { name: "Dry Hollow", latitude: -30, longitude: 135 };

test.beforeEach(() => places.resetSession());

test("a place needs coordinates in range; the name is one short line", () => {
    assert.deepStrictEqual(places.validPlace({ name: " Cinder\n Flats ", latitude: "41.5", longitude: -101.25 }),
        { name: "Cinder Flats", latitude: 41.5, longitude: -101.25 });
    assert.strictEqual(places.validPlace({ latitude: 1, longitude: 2 }).name, places.DEFAULT_NAME);
    assert.strictEqual(places.validPlace({ name: "x".repeat(200), latitude: 1, longitude: 2 }).name.length, places.MAX_NAME_LENGTH);
    for (const bad of [null, "Cinder", {}, { latitude: 91, longitude: 0 }, { latitude: 0, longitude: -181 },
        { latitude: "", longitude: 0 }, { latitude: "north", longitude: 0 }, { latitude: null, longitude: 0 }]) {
        assert.strictEqual(places.validPlace(bad), null, JSON.stringify(bad));
    }
});

test("places within about a kilometer are the same place", () => {
    assert.strictEqual(places.key(null), "home");
    assert.strictEqual(places.key(CINDER), "41.50,-101.25");
    assert.ok(places.samePlace(CINDER, { latitude: 41.5012, longitude: -101.2549 }));
    assert.ok(!places.samePlace(CINDER, HOLLOW));
    assert.ok(!places.samePlace(CINDER, null));
});

test("search results are named with their region, or their country", () => {
    const result = { name: "Cinder Flats", region: "North Province", country: "Exampleland" };
    assert.strictEqual(places.resultName(result), "Cinder Flats, North Province");
    assert.strictEqual(places.resultName({ name: "Cinder Flats", region: "", country: "Exampleland" }), "Cinder Flats, Exampleland");
    assert.strictEqual(places.resultName({ name: "Monaco", region: "Monaco", country: "Monaco" }), "Monaco");
    assert.strictEqual(places.resultDetail(result), "Cinder Flats, North Province, Exampleland");
    assert.strictEqual(places.resultDetail({ name: "Monaco", region: "Monaco", country: "Monaco" }), "Monaco");
});

test("the address can pin a place", () => {
    assert.deepStrictEqual(places.fromAddress("?lat=41.5&lon=-101.25&name=Cinder%20Flats"),
        { name: "Cinder Flats", latitude: 41.5, longitude: -101.25 });
    assert.strictEqual(places.fromAddress("?lat=41.5&lon=-101.25").name, places.DEFAULT_NAME);
    assert.strictEqual(places.fromAddress("?theme=ink"), null);
    assert.strictEqual(places.fromAddress("?lat=41.5"), null);
    assert.strictEqual(places.fromAddress("?lat=200&lon=0"), null);
});

test("choosing a place remembers it and puts it at the top of the saved list", () => {
    const storage = new Storage();
    assert.strictEqual(places.savedChoice(storage), null);
    assert.ok(places.choose(CINDER, storage));
    assert.ok(places.choose(HOLLOW, storage));
    assert.deepStrictEqual(places.savedChoice(storage), HOLLOW);
    assert.deepStrictEqual(places.savedPlaces(storage).map((place) => place.name), ["Dry Hollow", "Cinder Flats, North Province"]);
    // Choosing one again moves it up, once
    places.choose({ ...CINDER, latitude: 41.501 }, storage);
    assert.deepStrictEqual(places.savedPlaces(storage).map((place) => place.name), ["Cinder Flats, North Province", "Dry Hollow"]);
    // Home is a choice too, and keeps the list
    assert.ok(places.choose(null, storage));
    assert.strictEqual(places.savedChoice(storage), null);
    assert.strictEqual(places.savedPlaces(storage).length, 2);
});

test("at most MAX_SAVED places are kept, and anything unusable in storage is ignored", () => {
    const storage = new Storage();
    for (let index = 0; index < places.MAX_SAVED + 3; index += 1) {
        places.choose({ name: `Place ${index}`, latitude: index, longitude: index }, storage);
    }
    assert.strictEqual(places.savedPlaces(storage).length, places.MAX_SAVED);
    assert.strictEqual(places.savedPlaces(storage)[0].name, `Place ${places.MAX_SAVED + 2}`);

    storage.setItem(places.SAVED_KEY, "not json");
    storage.setItem(places.CHOICE_KEY, JSON.stringify({ latitude: "north" }));
    assert.deepStrictEqual(places.savedPlaces(storage), []);
    assert.strictEqual(places.savedChoice(storage), null);
    storage.setItem(places.SAVED_KEY, JSON.stringify([HOLLOW, "x", { latitude: 99, longitude: 0 }]));
    assert.deepStrictEqual(places.savedPlaces(storage), [HOLLOW]);
});

test("forgetting the chosen place goes back to home", () => {
    const storage = new Storage();
    places.choose(CINDER, storage);
    places.choose(HOLLOW, storage);
    places.forget(CINDER, storage);
    assert.deepStrictEqual(places.savedChoice(storage), HOLLOW);
    places.forget(HOLLOW, storage);
    assert.strictEqual(places.savedChoice(storage), null);
    assert.deepStrictEqual(places.savedPlaces(storage), []);
});

test("blocked storage keeps the choice until a reload", () => {
    const storage = new BlockedStorage();
    assert.strictEqual(places.choose(CINDER, storage), false);
    assert.deepStrictEqual(places.savedChoice(storage), CINDER);
    assert.deepStrictEqual(places.savedPlaces(storage), [CINDER]);
    places.resetSession();
    assert.strictEqual(places.savedChoice(storage), null);
});

test("which place is shown: the address, then this browser's choice while search is on, then home", () => {
    const storage = new Storage();
    assert.deepStrictEqual(places.current("", storage, true), { place: null, pinned: false });
    places.choose(CINDER, storage);
    assert.deepStrictEqual(places.current("", storage, true), { place: CINDER, pinned: false });
    // Search turned off: the choice is set aside, not forgotten
    assert.deepStrictEqual(places.current("", storage, false), { place: null, pinned: false });
    assert.deepStrictEqual(places.savedChoice(storage), CINDER);
    // A pinned place is still asked for (the server refuses it when search is off)
    const pinned = places.current("?lat=-30&lon=135&name=Dry%20Hollow", storage, false);
    assert.deepStrictEqual(pinned, { place: HOLLOW, pinned: true });
});

test("API addresses are relative and carry the place", () => {
    assert.strictEqual(places.weatherUrl(null), "api/weather");
    assert.strictEqual(places.weatherUrl(CINDER), "api/weather?lat=41.5&lon=-101.25&name=Cinder+Flats%2C+North+Province");
    assert.strictEqual(places.searchUrl("Cinder & Flats"), "api/places?q=Cinder+%26+Flats");
});

test("choosing a place takes the pinned one out of the address", () => {
    const calls = [];
    const win = {
        location: { href: "http://outpost.test/?theme=ink&lat=1&lon=2&name=Here" },
        history: { replaceState: (state, title, url) => calls.push(url) },
    };
    assert.ok(places.removeFromAddress(win));
    assert.deepStrictEqual(calls, ["http://outpost.test/?theme=ink"]);
    win.location.href = "http://outpost.test/?theme=ink";
    assert.ok(!places.removeFromAddress(win));
    assert.strictEqual(calls.length, 1);
});
