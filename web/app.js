// Outpost front end. Reads /data/weather.json (written by the updater)
// and renders the HUD. Key names must match outpost_updater.py.

const REFRESH_MS = 60 * 1000;          // how often the page re-reads the JSON
const STALE_AFTER_MS = 10 * 60 * 1000; // warn if data is older than this

// Only the icons that exist in assets/icons today. Extra condition names
// from future providers are mapped onto them until more icons are added.
const iconMap = {
    "sunny": "assets/icons/sunny.svg",
    "cloudy": "assets/icons/cloudy.svg",
    "partly-cloudy": "assets/icons/cloudy.svg",
    "rain": "assets/icons/rain.svg",
    "storm": "assets/icons/rain.svg",
    "snow": "assets/icons/unknown.svg",
    "fog": "assets/icons/unknown.svg",
    "unknown": "assets/icons/unknown.svg"
};

function iconFor(name) {
    return iconMap[name] || iconMap["unknown"];
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

        const icon = document.createElement("img");
        icon.className = "forecast-icon";
        icon.src = iconFor(period.icon);
        icon.alt = "";

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
        return;
    }

    alerts.forEach(alert => {
        const box = document.createElement("div");
        box.className = "detail-box";

        const title = document.createElement("strong");
        title.textContent = alert.title || "Alert";

        box.append(title, document.createElement("br"), document.createTextNode(alert.description || ""));
        container.appendChild(box);
    });
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
        setText("lastUpdated", formatDateTime(weather.generated_at));

        document.getElementById("currentIcon").src = iconFor(current.icon);

        const generated = new Date(weather.generated_at);
        const isStale = Number.isNaN(generated.getTime()) || (Date.now() - generated.getTime()) > STALE_AFTER_MS;
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

loadWeather();
setInterval(loadWeather, REFRESH_MS);
