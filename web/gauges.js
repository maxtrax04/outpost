// Outpost gauge values for themes.
// Every reading is also given to CSS as a number from 0 to 1, so a theme can draw dials and bars
// without any code: for example a needle turned by `calc(-135deg + var(--value) * 270deg)`.
// The 0..1 scale does not depend on units, so a theme keeps working whatever units are shown.
//
//   --wx-<name>  on the page root, for every reading below (for a gauge anywhere on the page)
//   --value      on the element with data-metric="<name>", which is also marked data-gauge, and
//                data-missing when the reading is not available (so a theme can hide its needle)
//   --wx-high, --wx-low, --wx-rain, --wx-uv  on each forecast card
//
// A missing or unreadable value removes the property, so `var(--value, 0)` picks the fallback.

(function (root) {
    "use strict";

    // name: [field in weather.json, value shown as 0, value shown as 1]. Values outside are clamped.
    const CURRENT = {
        "temperature": ["temperature_f", -20, 120],
        "feels-like": ["feels_like_f", -20, 120],
        "humidity": ["humidity_percent", 0, 100],
        "wind": ["wind_mph", 0, 60],
        "pressure": ["pressure_inhg", 28.5, 31],
        "uv": ["uv_index", 0, 11],
        "visibility": ["visibility_miles", 0, 10],
    };

    const FORECAST = {
        "high": ["high_f", -20, 120],
        "low": ["low_f", -20, 120],
        "rain": ["precipitation_percent", 0, 100],
        "uv": ["uv_index", 0, 11],
    };

    // A reading as 0..1, or null when there is no usable number
    function scale(value, low, high) {
        if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
        const number = Number(value);
        if (!Number.isFinite(number)) return null;
        return Math.min(1, Math.max(0, (number - low) / (high - low)));
    }

    function values(data, table) {
        const result = {};
        for (const [name, [field, low, high]] of Object.entries(table)) {
            result[name] = scale(data ? data[field] : null, low, high);
        }
        return result;
    }

    function setValue(element, property, value) {
        if (value === null) {
            element.style.removeProperty(property);
        } else {
            element.style.setProperty(property, value.toFixed(3));
        }
    }

    // Sets the current readings on the page; returns the 0..1 values
    function applyCurrent(current, doc) {
        doc = doc || document;
        const result = values(current, CURRENT);
        for (const [name, value] of Object.entries(result)) {
            setValue(doc.documentElement, `--wx-${name}`, value);
            for (const element of doc.querySelectorAll(`[data-metric="${name}"]`)) {
                setValue(element, "--value", value);
                element.toggleAttribute("data-gauge", true);
                element.toggleAttribute("data-missing", value === null);
            }
        }
        return result;
    }

    // Sets one forecast period's values on its card; returns the 0..1 values
    function applyForecast(card, period) {
        const result = values(period, FORECAST);
        for (const [name, value] of Object.entries(result)) {
            setValue(card, `--wx-${name}`, value);
        }
        return result;
    }

    const api = { CURRENT, FORECAST, scale, values, applyCurrent, applyForecast };

    root.OutpostGauges = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
