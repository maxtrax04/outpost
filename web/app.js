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

function formatTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "--";
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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

// Decides what to show for alerts: the list, a "none" panel, or a one-line note.
// A panel that is hidden because there are no alerts must never be mistaken for a
// failed check, so the one-line note says when alerts were last checked.
function renderAlertsSection(weather, config) {
    const panel = document.getElementById("alertsPanel");
    const note = document.getElementById("alertsStatus");
    const container = document.getElementById("alerts");

    const alerts = Array.isArray(weather.alerts) ? weather.alerts : [];
    const supported = weather.alerts_supported !== false;
    const alwaysShow = Boolean(config.ui && config.ui.alerts_always_show);
    const outdated = weather.status !== "ok";
    const checked = formatTime(weather.generated_at);

    if (supported && alerts.length > 0) {
        panel.hidden = false;
        note.hidden = true;
        renderAlerts(alerts);
        return;
    }

    // One wording for the panel, a shorter one for the note under the forecast
    let panelText;
    let noteText;
    if (!supported) {
        panelText = "Alerts are not provided by this data source";
        noteText = "Alerts: not provided by this data source";
    } else {
        panelText = `No active alerts (checked ${checked})`;
        noteText = `Alerts: none (checked ${checked})`;
    }
    if (outdated) {
        panelText += " - data may be out of date";
        noteText += " - data may be out of date";
    }

    if (alwaysShow) {
        container.textContent = panelText;
        panel.classList.remove("alert-active");
        panel.hidden = false;
        note.hidden = true;
    } else {
        panel.hidden = true;
        note.textContent = noteText;
        note.hidden = false;
    }
}

function renderSun(config) {
    const place = OutpostDim.coordinates(config);
    const times = place ? OutpostDim.sunTimes(new Date(), place.latitude, place.longitude) : null;

    let sunrise = "No coordinates";
    let sunset = "No coordinates";

    if (times && times.polar === "day") {
        sunrise = sunset = "Midnight sun";
    } else if (times && times.polar === "night") {
        sunrise = sunset = "Polar night";
    } else if (times) {
        sunrise = times.sunrise ? formatTime(times.sunrise) : "--";
        sunset = times.sunset ? formatTime(times.sunset) : "--";
    }

    setText("sunrise", sunrise);
    setText("sunset", sunset);
}

// OUTPOST_SUBTITLE: empty hides the line. {date} and {time} are replaced with the current date and time.
function renderSubtitle(config) {
    const element = document.getElementById("subtitle");
    const template = (config.ui && config.ui.subtitle) || "";
    const now = new Date();

    const text = template
        .replaceAll("{date}", now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }))
        .replaceAll("{time}", now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));

    element.textContent = text;
    element.hidden = text.trim() === "";
}

async function loadWeather(config) {
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
        renderAlertsSection(weather, config);
    } catch (error) {
        console.error("Unable to load Outpost data:", error);
        setText("condition", "Local data unavailable");
        setText("status", "OFFLINE");
        setBanner(true);

        const note = document.getElementById("alertsStatus");
        note.textContent = "Alerts: unavailable (no weather data)";
        note.hidden = false;
    }
}

// ---- Themes -----------------------------------------------------------
// The theme comes from ?theme=name in the URL (handy for previews), otherwise
// from data/config.json (written from OUTPOST_THEME), otherwise the default.
const DEFAULT_THEME = "retro-crt";

function validTheme(name) {
    return typeof name === "string" && /^[a-z0-9-]+$/.test(name) ? name : null;
}

// Reads data/config.json. If it has no usable coordinates (for example an old file written
// by an earlier version), the coordinates stored in weather.json are used instead, so
// sunrise, sunset, and sun-based dimming keep working.
async function loadConfig() {
    let config = {};

    try {
        const response = await fetch(`data/config.json?cacheBust=${Date.now()}`);
        if (response.ok) {
            config = await response.json();
        }
    } catch (error) {
        config = {};
    }

    if (!OutpostDim.coordinates(config)) {
        try {
            const response = await fetch(`data/weather.json?cacheBust=${Date.now()}`);
            if (response.ok) {
                const weather = await response.json();
                config.latitude = weather.coordinates && weather.coordinates.latitude;
                config.longitude = weather.coordinates && weather.coordinates.longitude;
            }
        } catch (error) {
            // Nothing more to try; the sun box will say there are no coordinates
        }
    }

    return config;
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
    renderSubtitle(config);
    renderSun(config);
    await loadWeather(config);
}

refresh();
setInterval(refresh, REFRESH_MS);
