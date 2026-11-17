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

    // Degrees the wind comes from -> one of 8 compass points ("SW"), or "" when not a number
    const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
    function compass(degrees) {
        if (typeof degrees !== "number" || !Number.isFinite(degrees)) return "";
        return COMPASS[Math.round((((degrees % 360) + 360) % 360) / 45) % 8];
    }

    // The wind reading: "SW 12 mph", "12 mph" without a direction, "Calm" at 0, or "--"
    function windText(current, unitLabels) {
        const speed = current ? current.wind_speed : null;
        if (typeof speed !== "number" || !Number.isFinite(speed)) return "--";
        if (speed === 0) return "Calm";
        const point = compass(current.wind_direction);
        const text = `${speed} ${(unitLabels || DEFAULT_UNITS).speed}`;
        return point ? `${point} ${text}` : text;
    }

    // The dew point line under the humidity ("Dew point 54°F"), or "" when there is none
    function dewPointText(current, unitLabels) {
        const dew = current ? current.dew_point : null;
        if (typeof dew !== "number" || !Number.isFinite(dew)) return "";
        return `Dew point ${dew}${(unitLabels || DEFAULT_UNITS).temperature}`;
    }

    // Readings older than this get their time shown ("Reading from 2:40 PM"). Stations often report
    // hourly, and a service's answer is reused for some minutes, so younger readings are normal.
    const OLD_READING_MS = 60 * 60 * 1000;

    // When the readings are from, if they are old enough to mention; otherwise null
    function oldReadingTime(weather, now) {
        const observed = weather && weather.current ? weather.current.observed_at : null;
        if (typeof observed !== "string") return null;
        const time = new Date(observed);
        if (Number.isNaN(time.getTime())) return null;
        const age = (now === undefined ? Date.now() : now) - time.getTime();
        return age > OLD_READING_MS ? time : null;
    }

    // Where the weather is read from, in order: the API (app/outpost_server.py), then data/weather.json
    // for a page served without it (an older proxy setup or a plain file server). Relative, so they
    // also work under a path prefix.
    const WEATHER_URLS = ["api/weather", "data/weather.json"];

    // An Error for an API answer that is not OK, with the API's own message when it sent one
    // ({"error": ..., "message": ...}); error.apiMessage is "" when it did not
    async function apiError(response) {
        let message = "";
        try {
            const body = await response.json();
            message = body && typeof body.message === "string" ? body.message.trim() : "";
        } catch (error) {
            // Not JSON (nginx's own 429 or 502 page, say)
        }
        const error = new Error(message || `HTTP ${response.status}`);
        error.status = response.status;
        error.apiMessage = message;
        return error;
    }

    // The first answer that works, from WEATHER_URLS; throws the last error if none does.
    // fetchFn is window.fetch (passed in, so tests can replace it); now keeps answers out of caches.
    // placeUrl is another place's address (OutpostPlaces.weatherUrl): it is asked for alone, since
    // falling back to data/weather.json would show home under the other place's name.
    async function fetchWeather(fetchFn, now, placeUrl) {
        if (placeUrl) {
            const response = await fetchFn(`${placeUrl}&cacheBust=${now}`);
            if (response.ok) return response;
            throw await apiError(response);
        }
        let lastError = new Error("no weather address");
        for (const url of WEATHER_URLS) {
            try {
                const response = await fetchFn(`${url}?cacheBust=${now}`);
                if (response.ok) return response;
                lastError = new Error(`HTTP ${response.status}`);
            } catch (error) {
                lastError = error;
            }
        }
        throw lastError;
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

    const api = {
        SCHEMA_VERSION, DEFAULT_UNITS, OLD_READING_MS, WEATHER_URLS, units, sourceText, alertsSupported,
        uncertainAlertsSource, gustText, compass, windText, dewPointText, oldReadingTime, fetchWeather, apiError,
    };

    root.OutpostData = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
