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

    const api = { SCHEMA_VERSION, DEFAULT_UNITS, units, sourceText, alertsSupported };

    root.OutpostData = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
