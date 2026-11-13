// Reading weather.json (docs/data-format.md): unit labels, data sources, and alerts.
// Kept apart from app.js so it can be tested without a page.

(function (root) {
    "use strict";

    // The weather.json format this dashboard reads
    const SCHEMA_VERSION = 1;

    // Used when weather.json has no "units" block (an error file, or one being written)
    const DEFAULT_UNITS = { system: "imperial", temperature: "°F", speed: "mph", pressure: "inHg", distance: "mi" };

    // The label for each kind of reading, from the "units" block
    function units(weather) {
        const given = weather && weather.units && typeof weather.units === "object" ? weather.units : {};
        const result = {};
        for (const [kind, fallback] of Object.entries(DEFAULT_UNITS)) {
            result[kind] = typeof given[kind] === "string" && given[kind] ? given[kind] : fallback;
        }
        return result;
    }

    // Names of the sources to credit, once each: weather, values filled from a second source, then alerts
    function sourceText(weather) {
        const sources = (weather && weather.sources) || {};
        const names = [];
        for (const entry of [sources.weather, sources.fill, sources.alerts]) {
            const name = entry && typeof entry.name === "string" ? entry.name.trim() : "";
            if (name && !names.includes(name)) names.push(name);
        }
        return names.length ? names.join("; ") : "--";
    }

    // False when the data source has no official alerts ("sources.alerts" is null)
    function alertsSupported(weather) {
        const sources = weather && weather.sources;
        return Boolean(sources && sources.alerts);
    }

    // The gust line under the wind ("Gusts 18 mph"), or "" when there is no gust stronger than the wind
    function gustText(current, unitLabels) {
        const gust = current ? current.wind_gust : null;
        const wind = current ? current.wind_speed : null;
        if (typeof gust !== "number" || !Number.isFinite(gust)) return "";
        if (typeof wind === "number" && gust <= wind) return "";
        return `Gusts ${gust} ${(unitLabels || DEFAULT_UNITS).speed}`;
    }

    // Alerts sources whose empty list can also mean "this country is not covered" (Pirate Weather's alerts
    // cover only the countries on the WMO alert hub), so "none" is said as "none reported by" them
    const UNCERTAIN_ALERTS_SOURCES = ["pirateweather"];

    // The name to give in "none reported by ...", or "" when an empty list really means no alerts
    function uncertainAlertsSource(weather) {
        const source = weather && weather.sources && weather.sources.alerts;
        if (!source || !UNCERTAIN_ALERTS_SOURCES.includes(source.id)) return "";
        return typeof source.name === "string" && source.name.trim() ? source.name.trim() : source.id;
    }

    const api = { SCHEMA_VERSION, DEFAULT_UNITS, units, sourceText, alertsSupported, uncertainAlertsSource, gustText };

    root.OutpostData = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
