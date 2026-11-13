// Outpost gauge values for themes.
// Every reading is also given to CSS as a number from 0 to 1, so a theme can draw dials and bars
// without any code: for example a needle turned by `calc(-135deg + var(--value) * 270deg)`.
// The 0..1 scale does not depend on units: metric readings are placed on the same scale, so a
// needle points to the same place whether the screen shows °F or °C.
//
//   --wx-<name>  on the page root, for every reading below (for a gauge anywhere on the page)
//   --value      on the element with data-metric="<name>", which is also marked data-gauge, and
//                data-missing when the reading is not available (so a theme can hide its needle)
//   --wx-high, --wx-low, --wx-rain, --wx-uv  on each forecast card
//
// A missing or unreadable value removes the property, so `var(--value, 0)` picks the fallback.

(function (root) {
    "use strict";

    // name: [field in weather.json, value shown as 0, value shown as 1, kind of unit]. The range is in
    // imperial units; values outside it are clamped.
    const CURRENT = {
        "temperature": ["temperature", -20, 120, "temperature"],
        "feels-like": ["feels_like", -20, 120, "temperature"],
        "humidity": ["humidity", 0, 100],
        "wind": ["wind_speed", 0, 60, "speed"],
        "pressure": ["pressure", 28.5, 31, "pressure"],
        "uv": ["uv_index", 0, 11],
        "visibility": ["visibility", 0, 10, "distance"],
    };

    const FORECAST = {
        "high": ["high", -20, 120, "temperature"],
        "low": ["low", -20, 120, "temperature"],
        "rain": ["precipitation_chance", 0, 100],
        "uv": ["uv_index", 0, 11],
    };

    // Metric readings in imperial units, to place them on the ranges above (app/units.py converts the other way)
    const FROM_METRIC = {
        temperature: (celsius) => celsius * 9 / 5 + 32,
        speed: (kmh) => kmh / 1.609344,
        pressure: (hpa) => hpa / 33.8638866667,
        distance: (km) => km / 1.609344,
    };

    // A reading as 0..1, or null when there is no usable number
    function scale(value, low, high) {
        if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
        const number = Number(value);
        if (!Number.isFinite(number)) return null;
        return Math.min(1, Math.max(0, (number - low) / (high - low)));
    }

    // system: the "system" of weather.json's units block; anything but "metric" is imperial
    function values(data, table, system) {
        const result = {};
        for (const [name, [field, low, high, kind]] of Object.entries(table)) {
            let value = data ? data[field] : null;
            if (system === "metric" && kind && typeof value === "number") value = FROM_METRIC[kind](value);
            result[name] = scale(value, low, high);
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
    function applyCurrent(current, doc, system) {
        doc = doc || document;
        const result = values(current, CURRENT, system);
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
    function applyForecast(card, period, system) {
        const result = values(period, FORECAST, system);
        for (const [name, value] of Object.entries(result)) {
            setValue(card, `--wx-${name}`, value);
        }
        return result;
    }

    const api = { CURRENT, FORECAST, FROM_METRIC, scale, values, applyCurrent, applyForecast };

    root.OutpostGauges = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
