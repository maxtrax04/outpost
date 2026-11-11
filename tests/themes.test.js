// Tests for the pure parts of web/themes.js. Run with: node --test
const test = require("node:test");
const assert = require("node:assert/strict");
const themes = require("../web/themes.js");

// A tiny stand-in for localStorage
const fakeStorage = (initial = {}) => {
    const data = { ...initial };
    return {
        getItem: (key) => (key in data ? data[key] : null),
        setItem: (key, value) => { data[key] = String(value); },
        removeItem: (key) => { delete data[key]; },
        data,
    };
};
const blockedStorage = () => ({
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
    removeItem() { throw new Error("blocked"); },
});

const config = {
    theme: "retro-crt",
    themes: [
        { id: "amber-terminal", name: "Amber Terminal" },
        { id: "modern-dark", name: "Modern Dark" },
        { id: "retro-crt", name: "Retro CRT" },
    ],
};

test("theme names are validated", () => {
    for (const good of ["retro-crt", "a", "theme-2", "maxtrax04/weather-desk"]) assert.equal(themes.validTheme(good), good);
    for (const bad of ["../etc", "Upper", "with space", "", null, undefined, 5, "a.css", "a/b/c", "/a", "a/", "a//b", "../a", "a/..", "User/theme"]) assert.equal(themes.validTheme(bad), null, String(bad));
});

test("each theme loads from its own folder", () => {
    assert.equal(themes.themeHref("modern-dark"), "themes/modern-dark/theme.css");
    assert.equal(themes.themeHref("maxtrax04/weather-desk"), "themes/maxtrax04/weather-desk/theme.css");
    for (const bad of ["../etc", "a/b/c", "", null]) assert.equal(themes.themeHref(bad), "themes/retro-crt/theme.css", String(bad));
});

test("available themes are read from the config and sanitized", () => {
    assert.deepEqual(themes.availableThemes(config).map((t) => t.id), ["amber-terminal", "modern-dark", "retro-crt"]);
    assert.equal(themes.availableThemes(config)[0].name, "Amber Terminal");
    assert.deepEqual(themes.availableThemes({}), []);
    assert.deepEqual(themes.availableThemes(null), []);
    assert.deepEqual(themes.availableThemes({ themes: "nope" }), []);
    const messy = { themes: [{ id: "ok", name: "Fine" }, { id: "../bad" }, null, { id: "no-name" }] };
    assert.deepEqual(themes.availableThemes(messy), [{ id: "ok", name: "Fine" }, { id: "no-name", name: "no-name" }]);
});

test("the server theme is used when nothing else is chosen", () => {
    const result = themes.chooseTheme(config, "", fakeStorage());
    assert.equal(result.wanted, "retro-crt");
    assert.equal(result.saved, null);
});

test("the default is used when the server gives none or an invalid one", () => {
    assert.equal(themes.chooseTheme({}, "", fakeStorage()).wanted, themes.DEFAULT_THEME);
    assert.equal(themes.chooseTheme({ theme: "../x" }, "", fakeStorage()).wanted, themes.DEFAULT_THEME);
});

test("a saved choice beats the server theme", () => {
    const storage = fakeStorage({ [themes.THEME_STORAGE_KEY]: "modern-dark" });
    const result = themes.chooseTheme(config, "", storage);
    assert.equal(result.wanted, "modern-dark");
    assert.equal(result.saved, "modern-dark");
});

test("the address beats a saved choice", () => {
    const storage = fakeStorage({ [themes.THEME_STORAGE_KEY]: "modern-dark" });
    const result = themes.chooseTheme(config, "?theme=amber-terminal", storage);
    assert.equal(result.wanted, "amber-terminal");
    assert.equal(result.fromAddress, "amber-terminal");
});

test("an invalid address value is ignored", () => {
    assert.equal(themes.chooseTheme(config, "?theme=../../etc", fakeStorage()).wanted, "retro-crt");
});

test("a saved theme the server no longer has is forgotten", () => {
    const storage = fakeStorage({ [themes.THEME_STORAGE_KEY]: "deleted-theme" });
    const result = themes.chooseTheme(config, "", storage);
    assert.equal(result.wanted, "retro-crt");
    assert.equal(storage.data[themes.THEME_STORAGE_KEY], undefined, "the stale value should be removed");
});

test("a saved theme is kept when the server did not send a theme list", () => {
    const storage = fakeStorage({ [themes.THEME_STORAGE_KEY]: "modern-dark" });
    assert.equal(themes.chooseTheme({ theme: "retro-crt" }, "", storage).wanted, "modern-dark");
});

test("garbage in storage is ignored", () => {
    const storage = fakeStorage({ [themes.THEME_STORAGE_KEY]: "../../etc/passwd" });
    assert.equal(themes.chooseTheme(config, "", storage).wanted, "retro-crt");
});

test("saving and clearing a choice", () => {
    const storage = fakeStorage();
    assert.equal(themes.writeSavedTheme("modern-dark", storage), true);
    assert.equal(themes.readSavedTheme(storage), "modern-dark");
    assert.equal(themes.writeSavedTheme(null, storage), true);
    assert.equal(themes.readSavedTheme(storage), null);
});

test("blocked storage never throws", () => {
    const storage = blockedStorage();
    assert.equal(themes.readSavedTheme(storage), null);
    assert.equal(themes.writeSavedTheme("modern-dark", storage), false);
    assert.equal(themes.chooseTheme(config, "", storage).wanted, "retro-crt");
});

// A tiny stand-in for the DOM: a parent holding <link> elements
const fakeDocument = () => {
    const children = [];
    const makeLink = () => {
        const link = {
            id: "", rel: "", href: "", sheet: null, onload: null, onerror: null,
            after(other) { children.splice(children.indexOf(link) + 1, 0, other); },
            remove() { const i = children.indexOf(link); if (i >= 0) children.splice(i, 1); },
        };
        return link;
    };
    const current = makeLink();
    current.id = "theme";
    current.href = "themes/retro-crt/theme.css";
    children.push(current);
    return { children, current, createElement: makeLink };
};

test("a theme loads in a new link that replaces the old one", async () => {
    const doc = fakeDocument();
    const pending = themes.loadStylesheet(doc.current, "themes/modern-dark/theme.css", 1000, doc);
    const next = doc.children[1];
    assert.equal(next.href, "themes/modern-dark/theme.css");
    next.onload();
    assert.equal(await pending, true);
    assert.deepEqual(doc.children, [next]);
    assert.equal(next.id, "theme");
});

test("a theme that fails to load is removed and the old one stays", async () => {
    const doc = fakeDocument();
    const pending = themes.loadStylesheet(doc.current, "themes/missing/theme.css", 1000, doc);
    doc.children[1].onerror();
    assert.equal(await pending, false);
    assert.deepEqual(doc.children, [doc.current]);
    assert.equal(doc.current.id, "theme");
});

test("a theme never holds up the page: the wait is capped", async () => {
    // No load or error event at all (what Chrome did when an existing link's href changed)
    const doc = fakeDocument();
    const parsed = themes.loadStylesheet(doc.current, "themes/modern-dark/theme.css", 20, doc);
    doc.children[1].sheet = {};
    assert.equal(await parsed, true);

    const doc2 = fakeDocument();
    const nothing = themes.loadStylesheet(doc2.current, "themes/modern-dark/theme.css", 20, doc2);
    assert.equal(await nothing, false);
    assert.deepEqual(doc2.children, [doc2.current]);
});
