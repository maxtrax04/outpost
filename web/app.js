// Outpost front end. Reads /data/weather.json (written by the updater)
// and renders the HUD. Key names must match outpost_updater.py
// and docs/data-format.md.

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

// Times follow OUTPOST_CLOCK (12- or 24-hour, or the device's region); see clock.js
function formatDateTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return OutpostClock.dateTime(date);
}

function formatTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "--";
    return OutpostClock.time(date);
}

function formatDay(value) {
    if (!value) return "--";
    // "2026-10-09" -> "Fri". Parse as local time to avoid off-by-one days.
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

// The state of the weather data on <html data-signal>, for themes: "waiting" until the first
// load (set in index.html), then "ok", "degraded" (old or partial data), or "offline" (none).
function setSignal(state) {
    document.documentElement.dataset.signal = state;
}

function setBanner(visible) {
    document.getElementById("alertBanner").classList.toggle("visible", visible);
}

function renderForecast(periods, system) {
    const container = document.getElementById("forecastContainer");
    container.replaceChildren();

    if (!Array.isArray(periods) || periods.length === 0) {
        const empty = document.createElement("div");
        empty.className = "forecast-card";
        empty.textContent = "No forecast available.";
        container.appendChild(empty);
        return;
    }

    const text = (className, value) => {
        const element = document.createElement("div");
        element.className = className;
        element.textContent = value;
        return element;
    };

    periods.slice(0, 5).forEach(period => {
        const card = document.createElement("div");
        card.className = "forecast-card";
        OutpostGauges.applyForecast(card, period, system);

        const day = text("forecast-day", formatDay(period.day));

        const iconWrap = document.createElement("div");
        iconWrap.className = "wx-glow forecast-icon-wrap";
        const icon = document.createElement("span");
        icon.className = "wx-icon forecast-icon";
        setIcon(icon, period.icon, period.condition);
        iconWrap.appendChild(icon);

        const condition = text("forecast-condition", period.condition || "Unknown");
        const temps = text("forecast-temps", `${valueOrDash(period.high, "°")} / ${valueOrDash(period.low, "°")}`);

        const extra = document.createElement("div");
        extra.className = "forecast-extra";
        extra.append(
            text("forecast-rain", `Rain: ${valueOrDash(period.precipitation_chance, "%")}`),
            text("forecast-uv", `UV: ${valueOrDash(period.uv_index)}`)
        );

        card.append(day, iconWrap, condition, temps, extra);
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
    let characters = 0;

    alerts.forEach(alert => {
        const severity = String(alert.severity || "unknown").toLowerCase();
        if (severity === "severe" || severity === "extreme") {
            serious = true;
        }

        const box = document.createElement("div");
        box.className = `detail-box alert-item severity-${severity}`;

        // Each part in its own element, so a theme can lay them out differently (on one line, say)
        const part = (tag, className, text) => {
            const element = document.createElement(tag);
            element.className = className;
            element.textContent = text;
            characters += text.length;
            return element;
        };

        box.append(part("strong", "alert-title", alert.title || "Alert"));
        box.append(document.createElement("br"), part("span", "alert-description", alert.description || ""));

        if (alert.expires) {
            box.append(document.createElement("br"), part("span", "alert-expires", `Until ${formatDateTime(alert.expires)}`));
        }

        container.appendChild(box);
    });

    container.parentElement.classList.toggle("alert-active", serious);
    // How much alert text there is, for a theme that scrolls it (to keep the speed readable)
    container.style.setProperty("--alert-chars", String(characters));
}

// Decides what to show for alerts: the list, a "none" panel, or a one-line note.
// A panel that is hidden because there are no alerts must never be mistaken for a
// failed check, so the one-line note says when alerts were last checked.
function renderAlertsSection(weather, config) {
    const panel = document.getElementById("alertsPanel");
    const note = document.getElementById("alertsStatus");
    const container = document.getElementById("alerts");

    const alerts = Array.isArray(weather.alerts) ? weather.alerts : [];
    const supported = OutpostData.alertsSupported(weather);
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
        .replaceAll("{time}", OutpostClock.time(now));

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
        const units = OutpostData.units(weather);

        setText("location", weather.location || "Unknown Location");
        setText("temperature", valueOrDash(current.temperature, units.temperature));
        setText("condition", current.condition || "Unknown");
        setText("feelsLike", valueOrDash(current.feels_like, units.temperature));
        setText("humidity", valueOrDash(current.humidity, "%"));
        setText("wind", valueOrDash(current.wind_speed, ` ${units.speed}`));
        setText("pressure", valueOrDash(current.pressure, ` ${units.pressure}`));
        setText("uv", valueOrDash(current.uv_index));
        setText("visibility", valueOrDash(current.visibility, ` ${units.distance}`));
        setText("source", OutpostData.sourceText(weather));
        setText("version", weather.version || "--");
        setText("lastUpdated", formatDateTime(weather.generated_at));

        setIcon(document.getElementById("currentIcon"), current.icon, current.condition);
        OutpostGauges.applyCurrent(current, document, units.system);

        // Data is stale after 3 missed updates (interval comes from the updater)
        const staleAfterMs = Math.max(MIN_STALE_MS, (weather.update_interval_seconds || 60) * 3 * 1000);
        const generated = new Date(weather.generated_at);
        const isStale = Number.isNaN(generated.getTime()) || (Date.now() - generated.getTime()) > staleAfterMs;
        const isOk = weather.status === "ok" && !isStale;

        setText("status", isOk ? "ONLINE" : "DEGRADED");
        setSignal(isOk ? "ok" : "degraded");
        setBanner(!isOk);

        renderForecast(weather.forecast, units.system);
        renderAlertsSection(weather, config);
    } catch (error) {
        console.error("Unable to load Outpost data:", error);
        setText("condition", "Local data unavailable");
        setText("status", "OFFLINE");
        setSignal("offline");
        setBanner(true);

        const note = document.getElementById("alertsStatus");
        note.textContent = "Alerts: unavailable (no weather data)";
        note.hidden = false;
    }
}

// ---- Settings -----------------------------------------------------------
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
    OutpostEffects.apply(config);
    OutpostClock.apply(config);
    await applyTheme(config);
    renderThemeSwitcher(config);
    renderSubtitle(config);
    renderSun(config);
    await loadWeather(config);
    OutpostFit.start();
}

refresh();
setInterval(refresh, REFRESH_MS);
