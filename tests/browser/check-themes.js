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
    }));
    // Values for theme gauges (web/gauges.js) reach the page
    if (state.gauges !== 6) problems.push(`${state.gauges} readings are marked as gauges, expected 6`);
    if (!/^0?\.\d+$|^[01](\.0+)?$/.test(state.humidity.trim())) problems.push(`--wx-humidity is "${state.humidity}", expected 0..1`);
    // The header shows the logo or the text title (the theme's --title-logo), never both or neither
    if ((state.logoHeight > 0) === (state.titleTextSize > 0)) {
        problems.push(`the title shows ${state.logoHeight > 0 ? "both the logo and the text" : "neither the logo nor the text"}`);
    }
    if (state.applied !== theme) problems.push(`theme applied is "${state.applied}", expected "${theme}"`);
    if (state.themeLinks !== 1) problems.push(`${state.themeLinks} theme stylesheets on the page, expected 1`);
    if (state.icons === 0) problems.push("no weather icons were set");
    if (state.fonts.length) problems.push(`fonts failed to load: ${state.fonts.join(", ")}`);

    if (SCREENSHOTS) await page.screenshot({ path: `${SCREENSHOTS}/${theme}-${name}.png` });
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
    }));
    const isReduced = (s) => s.effects === "reduced" && s.scanlines === "0" && s.glow === "none" && s.textShadow === "none";
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
    report("embedding from another site is blocked", await checkFraming(browser));

    await browser.close();
    console.log(failures ? `\n${failures} problem(s) found` : `\nAll ${themes.length} themes passed`);
    process.exit(failures ? 1 : 0);
})().catch((error) => {
    console.error(error);
    process.exit(1);
});
