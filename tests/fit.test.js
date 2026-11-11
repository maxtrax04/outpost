// Tests for web/fit.js. Run with: node --test tests/fit.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fit = require("../web/fit.js");

// A page that is `height` tall at full size, on a screen `available` tall
const page = (height, available) => (scale) => height * scale <= available;

test("off unless the theme or the address turns it on", () => {
    assert.equal(fit.wanted("", ""), false);
    assert.equal(fit.wanted("", " 0"), false);
    assert.equal(fit.wanted("", " 1"), true);
    assert.equal(fit.wanted("?fit=on", ""), true);
    assert.equal(fit.wanted("?fit=off", "1"), false);
    assert.equal(fit.wanted("?fit=maybe", "1"), true);
});

test("a page that already fits is not shrunk", () => {
    assert.equal(fit.chooseScale(page(700, 800)), 1);
});

test("a page that is too tall is shrunk just enough to fit", () => {
    const scale = fit.chooseScale(page(1000, 800));
    assert.ok(scale <= 0.8, `scale ${scale} is too large to fit`);
    assert.ok(scale > 0.795, `scale ${scale} shrinks more than needed`);
});

test("a page that would need tiny text is left to scroll", () => {
    assert.equal(fit.chooseScale(page(3000, 800)), null);
    assert.equal(fit.chooseScale(page(1000, 800), 0.9), null);
});

test("grows to fill a big screen only when the theme allows it", () => {
    assert.equal(fit.chooseScale(page(500, 1000)), 1);
    const scale = fit.chooseScale(page(500, 1000), fit.MIN_SCALE, 3);
    assert.ok(scale <= 2 && scale > 1.99, `scale ${scale} should be just under 2`);
    assert.equal(fit.chooseScale(page(100, 1000), fit.MIN_SCALE, 3), 3);
});

test("the theme's largest size is read safely", () => {
    assert.equal(fit.maxScale(""), 1);
    assert.equal(fit.maxScale(" 2.5"), 2.5);
    assert.equal(fit.maxScale("0.5"), 1);
    assert.equal(fit.maxScale("100"), 4);
    assert.equal(fit.maxScale("big"), 1);
});

test("never shrinks below the minimum", () => {
    const scale = fit.chooseScale(page(800 / fit.MIN_SCALE, 800));
    assert.ok(scale >= fit.MIN_SCALE);
});
