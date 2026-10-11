// Outpost front end. Reads /data/weather.json (written by the updater)
// and renders the HUD. Key names must match outpost_updater.py.

const REFRESH_MS = 60 * 1000;          // how often the page re-reads the JSON
const MIN_STALE_MS = 5 * 60 * 1000;    // never warn sooner than this

// Icon files in assets/icons/. Icons are monochrome and tinted with CSS
// (see .wx-icon in style.css), so themes can recolor them.
const ICONS = [
    "sunny", "clear-night", "partly-cloudy", "partly-cloudy-night", "cloudy",
    "fog", "drizzle", "rain", "sleet", "snow", "storm", "wind", "unknown"
];

function iconUrl(name) {
    return `url("assets/icons/${ICONS.includes(name) ? name : "unknown"}.svg")`;
}

function setIcon(element, name, label) {
    element.style.setProperty("--icon", iconUrl(name));
    element.setAttribute("role", "img");
    element.setAttribute("aria-label", label || name || "unknown");
}

function valueOrDash(value, suffix = "") {
    if (value === null || value === undefined || value === "") {
        return "--";
    }
    return `${value}${suffix}`;
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

function formatDateTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
    });
}

function formatDay(value) {
    if (!value) return "--";
    // "2026-10-09" -> "Fri". Parse as local time to avoid off-by-one days.
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

function setBanner(visible) {
    document.getElementById("alertBanner").classList.toggle("visible", visible);
}

function renderForecast(periods) {
    const container = document.getElementById("forecastContainer");
    container.replaceChildren();

    if (!Array.isArray(periods) || periods.length === 0) {
        const empty = document.createElement("div");
        empty.className = "forecast-card";
        empty.textContent = "No forecast available.";
        container.appendChild(empty);
        return;
    }

    periods.slice(0, 5).forEach(period => {
        const card = document.createElement("div");
        card.className = "forecast-card";

        const day = document.createElement("div");
        day.innerHTML = "<strong></strong>";
        day.firstChild.textContent = formatDay(period.day);

        const icon = document.createElement("div");
        icon.className = "wx-glow";
        const iconInner = document.createElement("span");
        iconInner.className = "wx-icon forecast-icon";
        setIcon(iconInner, period.icon, period.condition);
        icon.appendChild(iconInner);

        const condition = document.createElement("div");
        condition.className = "forecast-condition";
        condition.textContent = period.condition || "Unknown";

        const temps = document.createElement("div");
        temps.textContent = `${valueOrDash(period.high_f, "°")} / ${valueOrDash(period.low_f, "°")}`;

        const rain = document.createElement("div");
        rain.textContent = `Rain: ${valueOrDash(period.precipitation_percent, "%")}`;

        const uv = document.createElement("div");
        uv.textContent = `UV: ${valueOrDash(period.uv_index)}`;

        card.append(day, icon, condition, temps, rain, uv);
        container.appendChild(card);
    });
}

function renderAlerts(alerts) {
    const container = document.getElementById("alerts");
    container.replaceChildren();

    if (!Array.isArray(alerts) || alerts.length === 0) {
        container.textContent = "No active alerts in current Outpost data.";
        container.parentElement.classList.remove("alert-active");
        return;
    }

    let serious = false;

    alerts.forEach(alert => {
        const severity = String(alert.severity || "unknown").toLowerCase();
        if (severity === "severe" || severity === "extreme") {
            serious = true;
        }

        const box = document.createElement("div");
        box.className = `detail-box alert-item severity-${severity}`;

        const title = document.createElement("strong");
        title.textContent = alert.title || "Alert";

        box.append(title, document.createElement("br"), document.createTextNode(alert.description || ""));

        if (alert.expires) {
            box.append(document.createElement("br"), document.createTextNode(`Until ${formatDateTime(alert.expires)}`));
        }

        container.appendChild(box);
    });

    container.parentElement.classList.toggle("alert-active", serious);
}

async function loadWeather() {
    try {
        const response = await fetch(`data/weather.json?cacheBust=${Date.now()}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const weather = await response.json();
        const current = weather.current || {};

        setText("location", weather.location || "Unknown Location");
        setText("temperature", valueOrDash(current.temperature_f, "°F"));
        setText("condition", current.condition || "Unknown");
        setText("feelsLike", valueOrDash(current.feels_like_f, "°F"));
        setText("humidity", valueOrDash(current.humidity_percent, "%"));
        setText("wind", valueOrDash(current.wind_mph, " mph"));
        setText("pressure", valueOrDash(current.pressure_inhg, " inHg"));
        setText("uv", valueOrDash(current.uv_index));
        setText("visibility", valueOrDash(current.visibility_miles, " mi"));
        setText("provider", weather.provider || "--");
        setText("source", weather.source || "--");
        setText("version", weather.version || "--");
        setText("lastUpdated", formatDateTime(weather.generated_at));

        setIcon(document.getElementById("currentIcon"), current.icon, current.condition);

        // Data is stale after 3 missed updates (interval comes from the updater)
        const staleAfterMs = Math.max(MIN_STALE_MS, (weather.update_interval_seconds || 60) * 3 * 1000);
        const generated = new Date(weather.generated_at);
        const isStale = Number.isNaN(generated.getTime()) || (Date.now() - generated.getTime()) > staleAfterMs;
        const isOk = weather.status === "ok" && !isStale;

        setText("status", isOk ? "ONLINE" : "DEGRADED");
        setBanner(!isOk);

        renderForecast(weather.forecast);
        renderAlerts(weather.alerts);
    } catch (error) {
        console.error("Unable to load Outpost data:", error);
        setText("condition", "Local data unavailable");
        setText("status", "OFFLINE");
        setBanner(true);
    }
}

// ---- Themes -----------------------------------------------------------
// The theme comes from ?theme=name in the URL (handy for previews), otherwise
// from data/config.json (written from OUTPOST_THEME), otherwise the default.
const DEFAULT_THEME = "retro-crt";

function validTheme(name) {
    return typeof name === "string" && /^[a-z0-9-]+$/.test(name) ? name : null;
}

async function loadConfig() {
    try {
        const response = await fetch(`data/config.json?cacheBust=${Date.now()}`);
        return response.ok ? await response.json() : {};
    } catch (error) {
        return {};
    }
}

function loadStylesheet(link, href) {
    return new Promise(resolve => {
        link.onload = () => resolve(true);
        link.onerror = () => resolve(false);
        link.href = href;
    });
}

async function applyTheme(config) {
    try {
        const params = new URLSearchParams(window.location.search);
        const wanted = validTheme(params.get("theme")) || validTheme(config.theme) || DEFAULT_THEME;

        const link = document.getElementById("theme");
        const href = `themes/${wanted}.css`;

        if (link.getAttribute("href") !== href) {
            const loaded = await loadStylesheet(link, href);
            if (!loaded) {
                console.error(`Theme "${wanted}" not found; using ${DEFAULT_THEME}`);
                await loadStylesheet(link, `themes/${DEFAULT_THEME}.css`);
            }
        }

        document.documentElement.dataset.theme = wanted;
    } finally {
        document.body.classList.remove("theme-loading");
    }
}

// ---- Day/night dimming ------------------------------------------------
// Settings come from data/config.json (see dim.js). For testing, add
// ?dim=night, ?dim=day, or ?dim=0.5 (a brightness from 0 to 1) to the address.
function applyDim(config) {
    const override = new URLSearchParams(window.location.search).get("dim");
    const nightLevel = (config.dim && Number.isFinite(Number(config.dim.level)))
        ? Number(config.dim.level)
        : OutpostDim.DEFAULT_LEVEL;

    let brightness;
    if (override === "day") {
        brightness = 1;
    } else if (override === "night") {
        brightness = nightLevel;
    } else if (override !== null && Number.isFinite(Number(override))) {
        brightness = Math.min(1, Math.max(0, Number(override)));
    } else {
        brightness = OutpostDim.brightness(config, new Date());
    }

    document.documentElement.style.setProperty("--dim", brightness.toFixed(3));

    const overlay = document.getElementById("dim-overlay");
    if (overlay && !overlay.classList.contains("animated")) {
        requestAnimationFrame(() => requestAnimationFrame(() => overlay.classList.add("animated")));
    }
}

async function refresh() {
    const config = await loadConfig();
    applyDim(config);
    await applyTheme(config);
    await loadWeather();
}

refresh();
setInterval(refresh, REFRESH_MS);
