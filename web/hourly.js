// Outpost hourly forecast (#85): a strip of the next hours from weather.json "hourly", at the top of
// the forecast panel, above the days (#hourlyPanel). OUTPOST_HOURLY=false (config.json ui.hourly)
// hides it.
//
// Each hour is a .hourly-hour (role=listitem) with data-icon (the weather icon's name) and, on the hour under way,
// data-now, holding .hourly-time, a .wx-icon.hourly-icon, .hourly-temp, and .hourly-rain (with
// data-missing when the source gives no chance). The strip shows as many as fit on one line, up to
// SHOWN; hours that have already passed (in degraded data) are left out.

(function (root) {
    "use strict";

    const SHOWN = 12;
    const HOUR_MS = 60 * 60 * 1000;

    // When an entry ends: its `end` (OpenWeatherMap's free plan has 3-hour steps), else an hour on
    function endOf(hour, start) {
        const end = new Date(hour && hour.end).getTime();
        return Number.isFinite(end) && end > start ? end : start + HOUR_MS;
    }

    // The hours (or steps) that haven't ended at `now`, in order, at most `count`
    function upcoming(list, now, count = SHOWN) {
        if (!Array.isArray(list)) return [];
        return list
            .map((hour) => ({ hour, start: new Date(hour && hour.time).getTime() }))
            .filter((item) => Number.isFinite(item.start) && endOf(item.hour, item.start) > now)
            .sort((a, b) => a.start - b.start)
            .slice(0, count);
    }

    // "3 PM" or "15:00" (the dashboard's 12- or 24-hour clock), in the location's time zone
    function hourText(date, clock = "12", timeZone = null, locales = []) {
        const options = clock === "24"
            ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
            : { hour: "numeric", hourCycle: "h12" };
        if (timeZone) options.timeZone = timeZone;
        try {
            return date.toLocaleTimeString(locales, options);
        } catch (error) {
            return date.toLocaleTimeString(locales, { hour: "numeric" });
        }
    }

    function shown(value) {
        return typeof value === "number" && Number.isFinite(value);
    }

    // What one hour's cell shows
    function cellData(item, now, clock = "12", timeZone = null, locales = []) {
        const hour = item.hour || {};
        const current = item.start <= now;
        return {
            time: current ? "Now" : hourText(new Date(item.start), clock, timeZone, locales),
            now: current,
            icon: typeof hour.icon === "string" ? hour.icon : "unknown",
            condition: typeof hour.condition === "string" && hour.condition ? hour.condition : "Unknown",
            temperature: shown(hour.temperature) ? `${hour.temperature}°` : "--",
            rain: shown(hour.precipitation_chance) ? `${hour.precipitation_chance}%` : "--",
            rainMissing: !shown(hour.precipitation_chance),
        };
    }

    function cells(weather, now, clock, timeZone, locales) {
        return upcoming(weather && weather.hourly, now).map((item) => cellData(item, now, clock, timeZone, locales));
    }

    // Whether the strip is wanted at all (OUTPOST_HOURLY, on by default)
    function enabled(config) {
        return !(config && config.ui && config.ui.hourly === false);
    }

    function render(doc, weather, config, setIcon, now = Date.now()) {
        const panel = doc.getElementById("hourlyPanel");
        const list = doc.getElementById("hourly");
        if (!panel || !list) return;
        const clock = root.OutpostClock;
        const data = enabled(config)
            ? cells(weather, now, clock ? clock.effective() : "12", clock ? clock.getZone() : null)
            : [];
        list.replaceChildren(...data.map((cell) => {
            const box = doc.createElement("div");
            box.className = "hourly-hour";
            box.setAttribute("role", "listitem");
            box.dataset.icon = cell.icon;
            box.toggleAttribute("data-now", cell.now);
            const part = (className, text) => {
                const element = doc.createElement("span");
                element.className = className;
                element.textContent = text;
                return element;
            };
            const icon = doc.createElement("span");
            icon.className = "wx-icon hourly-icon";
            setIcon(icon, cell.icon, cell.condition);
            const rain = part("hourly-rain", cell.rain);
            rain.toggleAttribute("data-missing", cell.rainMissing);
            rain.title = "Chance of rain or snow";
            box.append(part("hourly-time", cell.time), icon, part("hourly-temp", cell.temperature), rain);
            return box;
        }));
        const hidden = data.length === 0;
        if (panel.hidden !== hidden) {
            panel.hidden = hidden;
            if (root.OutpostFit) root.OutpostFit.schedule();
        }
    }

    function clear(doc) {
        const list = doc.getElementById("hourly");
        if (list) list.replaceChildren();
    }

    const api = { SHOWN, upcoming, hourText, cellData, cells, enabled, render, clear };

    root.OutpostHourly = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
