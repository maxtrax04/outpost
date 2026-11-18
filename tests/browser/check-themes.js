// Loads the running dashboard in a real browser (headless Chromium) with every theme the server
// lists, under the real security headers, and fails if anything is blocked or does not render.
//
// Not part of `node --test`: it needs a running container and Playwright. CI runs it in the
// Docker smoke test. To run it yourself against a container on port 8088:
//
//   docker run --rm --network host -v "$PWD/tests/browser:/work" -w /work \
//     mcr.microsoft.com/playwright:v1.49.1-noble \
//     sh -c "npm install --silent --no-save playwright@1.49.1 && node check-themes.js"
//
// Settings (environment): OUTPOST_URL (default http://localhost:8088), SCREENSHOTS (a folder; optional).

const { chromium } = require("playwright");

const BASE = (process.env.OUTPOST_URL || "http://localhost:8088").replace(/\/$/, "");
const SCREENSHOTS = process.env.SCREENSHOTS || "";
const VIEWPORTS = { wide: { width: 1280, height: 800 }, phone: { width: 390, height: 844 } };

// Waits until fn(arg) is true in the page. (Playwright's page.waitForFunction polls by evaluating
// a string, which the page's Content-Security-Policy correctly refuses, so poll from here instead.)
async function waitFor(page, fn, arg, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await page.evaluate(fn, arg)) return true;
        await page.waitForTimeout(100);
    }
    return false;
}

let unitLabels = { temperature: "°F", speed: "mph" };

function endsWithNumberAnd(text, label) {
    return text.endsWith(label) && /\d/.test(text.slice(0, -label.length).trim().slice(-1));
}

async function checkTheme(browser, theme, name, viewport) {
    const page = await browser.newPage({ viewport });
    const problems = [];

    page.on("console", (message) => {
        if (message.type() === "error") problems.push(`console error: ${message.text()}`);
    });
    page.on("pageerror", (error) => problems.push(`script error: ${error.message}`));
    page.on("requestfailed", (request) => problems.push(`request failed: ${request.url()} (${(request.failure() || {}).errorText})`));
    page.on("response", (response) => {
        if (response.status() >= 400) problems.push(`HTTP ${response.status()}: ${response.url()}`);
    });
    await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (event) => {
            console.error(`blocked by the Content-Security-Policy: ${event.violatedDirective} ${event.blockedURI}`);
        });
    });

    await page.goto(`${BASE}/?theme=${theme}`, { waitUntil: "networkidle" });
    // The weather is rendered after the theme is applied, so this proves neither got stuck.
    // Well under the theme loader's 4-second cap, so a missed load event shows up as a failure.
    const rendered = await waitFor(page, () => /\d/.test(document.getElementById("temperature").textContent)
        && !document.body.classList.contains("theme-loading"), null, 3000);
    if (!rendered) problems.push("the weather never appeared (the page is stuck loading)");

    const state = await page.evaluate(() => ({
        applied: document.documentElement.dataset.theme,
        themeLinks: document.querySelectorAll('link[rel="stylesheet"][href*="themes/"]').length,
        icons: [...document.querySelectorAll(".wx-icon")]
            .filter((element) => getComputedStyle(element).getPropertyValue("--icon").includes("assets/icons/")).length,
        fonts: [...document.fonts].filter((font) => font.status === "error").map((font) => font.family),
        logoHeight: document.querySelector(".title-logo").getBoundingClientRect().height,
        titleTextSize: parseFloat(getComputedStyle(document.querySelector(".title-text")).fontSize),
        gauges: document.querySelectorAll(".detail-box[data-gauge]").length,
        humidity: getComputedStyle(document.documentElement).getPropertyValue("--wx-humidity"),
        temperature: document.getElementById("temperature").textContent,
        wind: document.getElementById("wind").textContent,
        source: document.getElementById("source").textContent,
    }));
    // Values for theme gauges (web/gauges.js) reach the page
    if (state.gauges !== 6) problems.push(`${state.gauges} readings are marked as gauges, expected 6`);
    if (!/^0?\.\d+$|^[01](\.0+)?$/.test(state.humidity.trim())) problems.push(`--wx-humidity is "${state.humidity}", expected 0..1`);
    // Unit labels and the source line come from weather.json (its "units" and "sources" blocks)
    if (!endsWithNumberAnd(state.temperature, unitLabels.temperature)) {
        problems.push(`the temperature reads "${state.temperature}", expected a number and ${unitLabels.temperature}`);
    }
    // "Calm" when the wind is 0, which the mock data picks now and then
    if (state.wind.trim() !== "Calm" && !endsWithNumberAnd(state.wind, unitLabels.speed)) {
        problems.push(`the wind reads "${state.wind}", expected "Calm" or a number and ${unitLabels.speed}`);
    }
    if (!state.source || state.source === "--") problems.push("the footer names no data source");
    // The header shows the logo or the text title (the theme's --title-logo), never both or neither
    if ((state.logoHeight > 0) === (state.titleTextSize > 0)) {
        problems.push(`the title shows ${state.logoHeight > 0 ? "both the logo and the text" : "neither the logo nor the text"}`);
    }
    if (state.applied !== theme) problems.push(`theme applied is "${state.applied}", expected "${theme}"`);
    if (state.themeLinks !== 1) problems.push(`${state.themeLinks} theme stylesheets on the page, expected 1`);
    if (state.icons === 0) problems.push("no weather icons were set");
    if (state.fonts.length) problems.push(`fonts failed to load: ${state.fonts.join(", ")}`);

    if (SCREENSHOTS) await page.screenshot({ path: `${SCREENSHOTS}/${theme.replace("/", "--")}-${name}.png` });
    await page.close();
    return problems;
}

async function checkSwitching(browser, themes) {
    // Switching back and forth with the on-screen switcher must not leave old stylesheets behind
    const page = await browser.newPage({ viewport: VIEWPORTS.wide });
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    const problems = [];
    for (const theme of [...themes].reverse()) {
        await page.click("#themeButton");
        await page.click(`.theme-option >> text="${theme.name}"`);
        if (!await waitFor(page, (id) => document.documentElement.dataset.theme === id, theme.id, 3000)) {
            problems.push(`switching to ${theme.id} did not apply it`);
        }
        await page.keyboard.press("Escape");
    }
    const links = await page.evaluate(() => document.querySelectorAll('link[rel="stylesheet"][href*="themes/"]').length);
    if (links !== 1) problems.push(`${links} theme stylesheets after switching, expected 1`);
    await page.close();
    return problems;
}

async function checkReducedEffects(browser) {
    // Reduced effects (web/effects.js): from the device setting, the address, and the viewer's toggle
    const problems = [];
    const effectsState = (page) => page.evaluate(() => ({
        effects: document.documentElement.dataset.effects,
        scanlines: getComputedStyle(document.body, "::before").opacity,
        glow: getComputedStyle(document.querySelector(".title-logo-glow")).filter,
        textShadow: getComputedStyle(document.body).textShadow,
        roll: getComputedStyle(document.querySelector(".scan-roll")).opacity,
        rolling: getComputedStyle(document.querySelector(".scan-roll"), "::before").animationName,
    }));
    const isReduced = (s) => s.effects === "reduced" && s.scanlines === "0" && s.glow === "none" && s.textShadow === "none"
        && s.roll === "0" && s.rolling === "none";
    const open = async (page, path) => {
        await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
        await waitFor(page, () => !document.body.classList.contains("theme-loading"), null, 3000);
        return effectsState(page);
    };

    // A device set to reduce motion gets reduced effects, and the page still renders
    let page = await browser.newPage({ viewport: VIEWPORTS.wide, reducedMotion: "reduce" });
    let state = await open(page, "/");
    if (!isReduced(state)) problems.push(`a device set to reduce motion got ${JSON.stringify(state)}`);
    if (!await waitFor(page, () => /\d/.test(document.getElementById("temperature").textContent), null, 3000)) {
        problems.push("the weather never appeared with reduced effects");
    }
    await page.close();

    page = await browser.newPage({ viewport: VIEWPORTS.wide, reducedMotion: "no-preference" });
    state = await open(page, "/");
    if (state.effects !== "full") problems.push(`effects are "${state.effects}" by default, expected full`);
    // The default theme has scanlines, so the rolling band shows and moves
    if (state.roll === "0" || state.rolling !== "scan-roll") problems.push(`the rolling band is missing by default: ${JSON.stringify(state)}`);
    state = await open(page, "/?effects=reduced");
    if (!isReduced(state)) problems.push(`?effects=reduced gave ${JSON.stringify(state)}`);

    // The checkbox in the theme panel turns them off, is remembered, and "Use server default" undoes it
    state = await open(page, "/");
    await page.click("#themeButton");
    await page.click("#effectsToggle");
    if (!await waitFor(page, () => document.documentElement.dataset.effects === "reduced", null, 2000)) {
        problems.push("the Reduced effects checkbox did not reduce effects");
    }
    if (await page.getAttribute("#effectsToggle", "aria-checked") !== "true") problems.push("the checkbox is not shown as checked");
    state = await open(page, "/");
    if (!isReduced(state)) problems.push(`the checkbox choice was not remembered after a reload: ${JSON.stringify(state)}`);
    await page.click("#themeButton");
    await page.click("#themeReset");
    if (!await waitFor(page, () => document.documentElement.dataset.effects === "full", null, 2000)) {
        problems.push('"Use server default" did not bring the effects back');
    }
    await page.close();
    return problems;
}

async function checkClock(browser) {
    // 12/24-hour clock (web/clock.js): the browser's language, the address, and the viewer's checkbox.
    // A US English browser uses 12-hour times on its own.
    const problems = [];
    const context = await browser.newContext({ viewport: VIEWPORTS.wide, locale: "en-US" });
    const page = await context.newPage();
    const updated = () => page.evaluate(() => document.getElementById("lastUpdated").textContent);
    const open = async (path) => {
        await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
        await waitFor(page, () => /\d/.test(document.getElementById("lastUpdated").textContent), null, 3000);
        return updated();
    };
    // A time may end with the location's zone ("12:29 PM GMT+9") when it differs from the browser's
    const withoutZone = (text) => text.replace(/\s+(GMT|UTC)[+-]?[\d:]*$|\s+(?!AM$|PM$)[A-Z]{2,5}$/, "");
    const is12 = (text) => /\d\s?[AP]M$/i.test(withoutZone(text));
    const is24 = (text) => /\b\d\d:\d\d$/.test(withoutZone(text));

    let text = await open("/");
    if (!is12(text)) problems.push(`a US English browser showed "${text}", expected a 12-hour time`);
    text = await open("/?clock=24");
    if (!is24(text)) problems.push(`?clock=24 showed "${text}"`);

    // The checkbox switches to 24-hour, is remembered, and "Use server default" undoes it
    await open("/");
    await page.click("#themeButton");
    await page.click("#clockToggle");
    if (!await waitFor(page, () => /\b\d\d:\d\d(\s+(GMT|UTC)[+-]?[\d:]*|\s+(?!AM$|PM$)[A-Z]{2,5})?$/.test(document.getElementById("lastUpdated").textContent), null, 3000)) {
        problems.push(`the 24-hour clock checkbox did not change the times ("${await updated()}")`);
    }
    if (await page.getAttribute("#clockToggle", "aria-checked") !== "true") problems.push("the clock checkbox is not shown as checked");
    text = await open("/");
    if (!is24(text)) problems.push(`the clock choice was not remembered after a reload ("${text}")`);
    await page.click("#themeButton");
    await page.click("#themeReset");
    if (!await waitFor(page, () => /\d\s?[AP]M(\s+(GMT|UTC)[+-]?[\d:]*|\s+[A-Z]{2,5})?$/i.test(document.getElementById("lastUpdated").textContent), null, 3000)) {
        problems.push(`"Use server default" did not bring back 12-hour times ("${await updated()}")`);
    }
    await context.close();
    return problems;
}

async function checkLocation(browser) {
    // Location search (web/places.js, web/place-panel.js): a place pinned in the address, searching,
    // remembering the choice, and going back to home. On by default (OUTPOST_LOCATION_SEARCH).
    const problems = [];
    const status = await (await fetch(`${BASE}/api/status`)).json();
    if (status.location_search !== true) return [`/api/status says ${JSON.stringify(status)}; location search should be on by default`];

    const page = await browser.newPage({ viewport: VIEWPORTS.phone });
    page.on("pageerror", (error) => problems.push(`script error: ${error.message}`));
    page.on("console", (message) => {
        if (message.type() === "error") problems.push(`console error: ${message.text()}`);
    });
    const shows = (name) => waitFor(page, (expected) => document.getElementById("location").textContent === expected
        && /\d/.test(document.getElementById("temperature").textContent), name, 5000);
    const location = () => page.evaluate(() => document.getElementById("location").textContent);

    await page.goto(`${BASE}/?lat=-30&lon=135&name=Dry%20Hollow`, { waitUntil: "networkidle" });
    if (!await shows("Dry Hollow")) problems.push(`a place pinned in the address showed "${await location()}"`);

    // The geocoding answer is made up here, so the check needs no internet
    await page.route("**/api/places?*", (route) => route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
            places: [{ name: "Cinder Flats", region: "North Province", country: "Exampleland", latitude: 41.5,
                longitude: -101.25, timezone: "America/Chicago" }],
            source: { id: "openmeteo", name: "Open-Meteo.com" },
        }),
    }));
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    await waitFor(page, () => /\d/.test(document.getElementById("temperature").textContent), null, 3000);
    const home = await location();

    await page.click("#themeButton");
    if (await page.isHidden("#placeSection")) {
        problems.push("the panel has no location search");
        await page.close();
        return problems;
    }
    await page.fill("#placeQuery", "Cinder");
    await page.press("#placeQuery", "Enter");
    try {
        await page.click(".place-result", { timeout: 3000 });
        if (!await shows("Cinder Flats, North Province")) problems.push(`a place chosen from the search showed "${await location()}"`);
    } catch (error) {
        problems.push(`the search showed no results (${(await page.textContent("#placeNote")) || "no note"})`);
    }

    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    if (!await shows("Cinder Flats, North Province")) problems.push(`the chosen place was not remembered after a reload ("${await location()}")`);

    await page.click("#themeButton");
    if (await page.locator(".place-forget").count() !== 1) problems.push("the chosen place is not in the saved list");
    await page.click(".place-option >> nth=0"); // Home
    if (!await shows(home)) problems.push(`choosing Home showed "${await location()}", expected "${home}"`);
    await page.close();
    return problems;
}

async function checkMyLocation(browser) {
    // "Use my location" (#31). Browsers share a location only with HTTPS pages and localhost, so
    // OUTPOST_URL must be one of those (CI uses localhost); otherwise the panel says HTTPS is needed.
    const problems = [];
    const position = { latitude: 41.50123, longitude: -101.25678 };

    let context = await browser.newContext({ viewport: VIEWPORTS.phone, geolocation: position, permissions: ["geolocation"] });
    let page = await context.newPage();
    page.on("pageerror", (error) => problems.push(`script error: ${error.message}`));
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    await page.click("#themeButton");
    if (await page.isHidden("#myLocation")) {
        problems.push("there is no Use my location button");
    } else {
        await page.click("#myLocation");
        const shown = await waitFor(page, () => document.getElementById("location").textContent === "My location"
            && /\d/.test(document.getElementById("temperature").textContent), null, 5000);
        if (!shown) problems.push(`Use my location showed "${await page.textContent("#location")}" (${await page.textContent("#placeNote")})`);
        const stored = await page.evaluate(() => window.localStorage.getItem("outpost.place") || "");
        if (stored.includes("41.501") || !stored.includes("41.5")) problems.push(`my location was stored as ${stored}, not rounded to 2 decimals`);
    }
    await context.close();

    // Refused: the panel says so instead of failing silently
    context = await browser.newContext({ viewport: VIEWPORTS.phone, permissions: [] });
    page = await context.newPage();
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    await page.click("#themeButton");
    await page.click("#myLocation");
    if (!await waitFor(page, () => /blocked|could not|too long/.test(document.getElementById("placeNote").textContent), null, 20000)) {
        problems.push(`a refused location said "${await page.textContent("#placeNote")}"`);
    }
    await context.close();
    return problems;
}

// A one-pixel PNG of one color, for a made-up radar tile
function pixelPng([red, green, blue, alpha]) {
    const zlib = require("zlib");
    const crcTable = Array.from({ length: 256 }, (_, n) => {
        let c = n;
        for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        return c >>> 0;
    });
    const crc = (bytes) => {
        let c = 0xffffffff;
        for (const byte of bytes) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
        return (c ^ 0xffffffff) >>> 0;
    };
    const chunk = (type, data) => {
        const length = Buffer.alloc(4);
        length.writeUInt32BE(data.length);
        const body = Buffer.concat([Buffer.from(type), data]);
        const check = Buffer.alloc(4);
        check.writeUInt32BE(crc(body));
        return Buffer.concat([length, body, check]);
    };
    const header = Buffer.alloc(13);
    header.writeUInt32BE(1, 0);
    header.writeUInt32BE(1, 4);
    header.set([8, 6, 0, 0, 0], 8); // 8-bit RGBA
    return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", header),
        chunk("IDAT", zlib.deflateSync(Buffer.from([0, red, green, blue, alpha]))), chunk("IEND", Buffer.alloc(0))]);
}

async function checkMap(browser) {
    // The map panel (web/map.js). Off by default, so the panel is hidden; then turned on in this
    // page only, with a made-up tile (mvt-fixture.js), so the check never asks OpenStreetMap.
    const problems = [];
    const { sampleTile } = require("./mvt-fixture.js");
    const page = await browser.newPage({ viewport: VIEWPORTS.wide });
    page.on("pageerror", (error) => problems.push(`script error: ${error.message}`));
    page.on("console", (message) => {
        if (message.type() === "error") problems.push(`console error: ${message.text()}`);
    });

    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    const config = await (await fetch(`${BASE}/data/config.json`)).json();
    if (!config.map || config.map.enabled) problems.push(`config.json map block is ${JSON.stringify(config.map)}, expected the map off by default`);
    if (!await page.isHidden("#mapPanel")) problems.push("the map panel shows although the map is off");

    let tilesAsked = 0;
    await page.route("**/data/config.json*", async (route) => {
        const response = await route.fetch();
        const body = await response.json();
        body.map = { ...body.map, enabled: true, zoom: 7, radar: true, radar_loop: false };
        await route.fulfill({ response, json: body });
    });
    await page.route("**/tiles/base/7/*/*.mvt", (route) => {
        tilesAsked += 1;
        route.fulfill({ contentType: "application/vnd.mapbox-vector-tile", body: Buffer.from(sampleTile()) });
    });
    // The radar: one made-up frame whose tiles are solid red
    let radarTilesAsked = 0;
    await page.route("**/api/radar*", (route) => route.fulfill({ json: { source: "noaa", credit: "NOAA",
        credit_url: "https://www.nssl.noaa.gov/projects/mrms/", zoom: 7,
        frames: [{ time: "2027-01-15T10:00:00Z", tiles: "tiles/radar/noaa/conus/20270115T100000Z/{z}/{x}/{y}.png" }] } }));
    await page.route("**/tiles/radar/noaa/conus/20270115T100000Z/7/*/*.png", (route) => {
        radarTilesAsked += 1;
        route.fulfill({ contentType: "image/png", body: pixelPng([255, 0, 0, 255]) });
    });
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    if (!await waitFor(page, () => !document.getElementById("mapPanel").hidden
        && document.getElementById("mapCanvas").width > 0, null, 5000)) {
        problems.push("the map panel did not draw once the map was on");
    } else {
        // Something besides the land color was drawn
        const colors = await page.evaluate(() => {
            const canvas = document.getElementById("mapCanvas");
            const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
            const seen = new Set();
            for (let index = 0; index < data.length && seen.size < 5; index += 4 * 97) seen.add(`${data[index]},${data[index + 1]},${data[index + 2]}`);
            return seen.size;
        });
        if (colors < 2) problems.push("the map canvas is one flat color");
        if (tilesAsked === 0) problems.push("no tiles were asked for");
        if (!(await page.textContent("#mapCredit")).includes("OpenStreetMap")) problems.push("the map does not credit OpenStreetMap");

        if (!await waitFor(page, () => !document.getElementById("radarCredit").hidden, null, 5000)) {
            problems.push("the radar was not shown");
        } else {
            if (radarTilesAsked === 0) problems.push("no radar tiles were asked for");
            if ((await page.textContent("#radarCredit")) !== "Radar: NOAA") problems.push("the radar does not credit NOAA");
            if (!/^RADAR \d/.test(await page.textContent("#radarTime"))) problems.push("the radar's time is not shown");
            // Red radar, drawn see-through over the map, away from the names at the center
            const red = await page.evaluate(() => {
                const canvas = document.getElementById("mapCanvas");
                const [r, g, b] = canvas.getContext("2d").getImageData(5, Math.round(canvas.height / 2), 1, 1).data;
                return r > 150 && r > g + 60 && r > b + 60;
            });
            if (!red) problems.push("the radar was not drawn on the map");
        }
    }
    // Without the route, the real server refuses other zooms and answers 404 while the map is off
    const status = (await fetch(`${BASE}/tiles/base/7/0/0.mvt`)).status;
    if (status !== 404) problems.push(`with the map off, /tiles/ answered ${status}, expected 404`);
    const radarStatus = (await fetch(`${BASE}/tiles/radar/rainviewer/abc123/7/0/0.png`)).status;
    if (radarStatus !== 404) problems.push(`with the map off, /tiles/radar/ answered ${radarStatus}, expected 404`);
    const radarApi = await fetch(`${BASE}/api/radar`);
    if (radarApi.status !== 404) problems.push(`with the map off, /api/radar answered ${radarApi.status}, expected 404`);
    await page.close();
    return problems;
}

async function checkFraming(browser) {
    // A page on another site must not be able to show the dashboard in a frame
    const page = await browser.newPage();
    let blocked = false;
    page.on("console", (message) => {
        if (/frame-ancestors/.test(message.text())) blocked = true;
    });
    await page.setContent(`<iframe src="${BASE}/" width="400" height="300"></iframe>`);
    await page.waitForTimeout(2000);
    await page.close();
    return blocked ? [] : ["another site was able to show the dashboard in a frame"];
}

(async () => {
    const config = await (await fetch(`${BASE}/data/config.json`)).json();
    const themes = config.themes || [];
    // The unit labels the page should show (weather.json's "units" block)
    const weather = await (await fetch(`${BASE}/data/weather.json`)).json();
    unitLabels = weather.units;
    if (themes.length === 0) throw new Error("config.json lists no themes");

    const browser = await chromium.launch();
    let failures = 0;
    const report = (label, problems) => {
        console.log(`${problems.length ? "FAIL" : "ok  "} ${label}`);
        for (const problem of problems) console.log(`       ${problem}`);
        failures += problems.length;
    };

    for (const theme of themes) {
        for (const [name, viewport] of Object.entries(VIEWPORTS)) {
            report(`${theme.id} (${name})`, await checkTheme(browser, theme.id, name, viewport));
        }
    }
    report("switching themes with the on-screen switcher", await checkSwitching(browser, themes));
    report("reduced effects (device setting, address, and checkbox)", await checkReducedEffects(browser));
    report("12/24-hour clock (language, address, and checkbox)", await checkClock(browser));
    report("location search (address, search, saved choice, home)", await checkLocation(browser));
    report("my location (allowed and refused)", await checkMyLocation(browser));
    report("map panel (off by default; drawn when on)", await checkMap(browser));
    report("embedding from another site is blocked", await checkFraming(browser));

    await browser.close();
    console.log(failures ? `\n${failures} problem(s) found` : `\nAll ${themes.length} themes passed`);
    process.exit(failures ? 1 : 0);
})().catch((error) => {
    console.error(error);
    process.exit(1);
});
