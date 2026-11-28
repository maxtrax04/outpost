// Takes the README's screenshots (#37) from a running dashboard: every built-in theme on a wide
// screen, and the default theme on a phone. Run by scripts/screenshots.sh, which starts a container
// with the mock data at the example location (Goodsprings, NV), the map on, and the theme button
// hidden. Uses the bundled font, like any visitor.
//
// Settings (environment): OUTPOST_URL (default http://localhost:8088), SCREENSHOTS (the folder to
// write to, default ./screenshots).

const fs = require("fs");
const { chromium } = require("playwright");

const BASE = (process.env.OUTPOST_URL || "http://localhost:8088").replace(/\/$/, "");
const OUT = process.env.SCREENSHOTS || "screenshots";
const WIDE = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };
const BUILT_IN = ["retro-crt", "amber-terminal", "command-center", "modern-dark", "field-station", "atomic-broadcast", "ink"];

// Playwright's page.waitForFunction is refused by the page's Content-Security-Policy, so poll from here
async function waitFor(page, fn, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await page.evaluate(fn)) return true;
        await page.waitForTimeout(200);
    }
    return false;
}

// The mock provider's readings are random (snow at 77°F, say), so the pictures get a fixed, likely
// late-autumn day in the Mojave instead, keeping the mock's current times. Still made up, and the
// footer still credits the mock provider. Air quality uses the US index without pollen, as
// Open-Meteo gives for a place in the US; one sample alert shows the alerts panel.
const DAYS = [
    ["Clear sky", "sunny", 66, 41, 0, 0, 4],
    ["Partly cloudy", "partly-cloudy", 63, 43, 5, 0, 4],
    ["Windy", "wind", 58, 38, 10, 0, 3],
    ["Light rain", "rain", 54, 40, 60, 0.12, 2],
    ["Clear sky", "sunny", 60, 37, 5, 0, 4],
];
const HOURS = [62, 60, 57, 54, 52, 50, 49, 47, 46, 45, 44, 43, 42, 42, 41, 41, 42, 45, 50, 55, 59, 62, 64, 65];

function isNight(time) {
    const hour = Number(new Date(time).toLocaleString("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", hour12: false }));
    return hour >= 17 || hour < 7;
}

function showcase(data) {
    const now = data.current.observed_at || data.generated_at;
    data.current = { ...data.current, temperature: 62, feels_like: 60, condition: "Clear sky", icon: isNight(now) ? "clear-night" : "sunny",
        humidity: 22, wind_speed: 9, wind_gust: 18, wind_direction: 225, dew_point: 25, pressure: 30.04,
        uv_index: isNight(now) ? 0 : 3, visibility: 10 };
    // The mock counts days in UTC; a real provider starts with today where the place is
    const today = new Date(new Date(now).toLocaleString("en-US", { timeZone: "America/Los_Angeles" }));
    data.forecast = data.forecast.map((day, index) => {
        const [condition, icon, high, low, chance, amount, uv] = DAYS[index % DAYS.length];
        const date = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate() + index)).toISOString().slice(0, 10);
        return { ...day, day: date, condition, icon, high, low, precipitation_chance: chance, precipitation: amount, uv_index: uv };
    });
    data.hourly = data.hourly.map((hour, index) => {
        return { ...hour, temperature: HOURS[index % HOURS.length], condition: "Clear sky", icon: isNight(hour.time) ? "clear-night" : "sunny",
            precipitation_chance: 0, precipitation: 0, wind_speed: 8 };
    });
    const sample = (data.alerts || []).find((alert) => alert.severity === "moderate");
    data.alerts = sample ? [sample] : [];
    if (data.air_quality) {
        data.air_quality = { ...data.air_quality, index: 38, scale: "us", category: "good", level: 0, us_aqi: 38, pollen: null };
    }
    return data;
}

async function shoot(browser, theme, viewport, path, options = {}) {
    const context = await browser.newContext({ viewport, locale: "en-US", timezoneId: "America/Los_Angeles",
        deviceScaleFactor: 1, isMobile: !!options.phone, hasTouch: !!options.phone });
    const page = await context.newPage();
    for (const address of ["**/data/weather.json*", "**/api/weather*"]) {
        await page.route(address, async (route) => {
            const response = await route.fetch();
            if (!response.ok()) return route.fulfill({ response });
            return route.fulfill({ response, json: showcase(await response.json()) });
        });
    }
    await page.goto(`${BASE}/?theme=${theme}`, { waitUntil: "networkidle" });
    const ready = await waitFor(page, () => /\d/.test(document.getElementById("temperature").textContent)
        && !document.body.classList.contains("theme-loading") && document.fonts.status === "loaded", 10000);
    if (!ready) throw new Error(`${theme}: the dashboard never finished loading`);
    // The map and radar tiles come in after the weather
    await waitFor(page, () => {
        const panel = document.getElementById("mapPanel");
        return !panel || panel.hidden || document.getElementById("mapCanvas").width > 0;
    }, 10000);
    await page.waitForTimeout(4000);
    const font = await page.evaluate(() => [...document.fonts].some((face) => /Share Tech Mono/i.test(face.family) && face.status === "loaded"));
    await page.screenshot({ path });
    await context.close();
    console.log(`${path}${font ? "" : " (Share Tech Mono not used by this theme)"}`);
}

(async () => {
    fs.mkdirSync(`${OUT}/themes`, { recursive: true });
    const browser = await chromium.launch();
    try {
        for (const theme of BUILT_IN) await shoot(browser, theme, WIDE, `${OUT}/themes/${theme}.png`);
        await shoot(browser, "retro-crt", PHONE, `${OUT}/phone.png`, { phone: true });
    } finally {
        await browser.close();
    }
})().catch((error) => {
    console.error(error.message);
    process.exit(1);
});
