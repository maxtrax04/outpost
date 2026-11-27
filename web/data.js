// Reading weather.json (docs/data-format.md): unit labels, data sources, and alerts.
// Kept apart from app.js so it can be tested without a page.

(function (root) {
    "use strict";

    // The weather.json format this dashboard reads
    const SCHEMA_VERSION = 1;

    // Used when weather.json has no "units" block (an error file, or one being written)
    const DEFAULT_UNITS = {
        system: "imperial", temperature: "°F", speed: "mph", pressure: "inHg", distance: "mi", precipitation: "in",
    };

    // The label for each kind of reading, from the "units" block. Files from before 0.8.0 have no
    // precipitation label, so a metric one gets "mm".
    function units(weather) {
        const given = weather && weather.units && typeof weather.units === "object" ? weather.units : {};
        const result = {};
        for (const [kind, fallback] of Object.entries(DEFAULT_UNITS)) {
            result[kind] = typeof given[kind] === "string" && given[kind] ? given[kind] : fallback;
        }
        if (!(typeof given.precipitation === "string" && given.precipitation) && result.system === "metric") {
            result.precipitation = "mm";
        }
        return result;
    }

    // A forecast day's expected rain or snow ("0.30 in", "7.6 mm"), or "" when none is expected or the
    // source doesn't say
    function amountText(value, unitLabels) {
        if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return "";
        const labels = unitLabels || DEFAULT_UNITS;
        return `${value.toFixed(labels.system === "metric" ? 1 : 2)} ${labels.precipitation}`;
    }

    // An alert's time line (#87), with `format` turning a Date into text: "Until <end>" for one in
    // effect, "From <start> until <end>" (or "From <start>") for one that hasn't started at `now`, or ""
    // when neither time is known. upcoming is true for one that hasn't started.
    function alertTime(alert, now, format) {
        const time = (value) => {
            if (typeof value !== "string" || !value) return null;
            const date = new Date(value);
            return Number.isNaN(date.getTime()) ? null : date;
        };
        const onset = time(alert && alert.onset);
        const expires = time(alert && alert.expires);
        const upcoming = Boolean(onset && onset.getTime() > now);
        let text = "";
        if (upcoming) {
            text = expires ? `From ${format(onset)} until ${format(expires)}` : `From ${format(onset)}`;
        } else if (expires) {
            text = `Until ${format(expires)}`;
        }
        return { text, upcoming };
    }

    // Air quality (#88): the names of the index scales and of their bands (weather.json air_quality)
    const AIR_SCALES = { us: "US AQI", european: "European AQI" };
    const AIR_CATEGORIES = {
        "good": "Good", "fair": "Fair", "moderate": "Moderate", "unhealthy-sensitive": "Unhealthy for sensitive groups",
        "unhealthy": "Unhealthy", "very-unhealthy": "Very unhealthy", "hazardous": "Hazardous", "poor": "Poor",
        "very-poor": "Very poor", "extremely-poor": "Extremely poor",
    };
    const POLLEN_NAMES = { alder: "alder", birch: "birch", grass: "grass", mugwort: "mugwort", olive: "olive", ragweed: "ragweed" };

    // The air quality box's text: { value: "57 Moderate", note: "US AQI · Pollen: grass 49, birch 12" },
    // or null when there is no index to show (the box is then hidden). Pollen lists the two most
    // plentiful kinds, only when there is some (at least 1 grain/m³).
    function airQualityText(air) {
        if (!air || typeof air !== "object") return null;
        const index = typeof air.index === "number" && Number.isFinite(air.index) ? Math.round(air.index) : null;
        if (index === null) return null;
        const band = AIR_CATEGORIES[air.category];
        const parts = [AIR_SCALES[air.scale] || "AQI"];
        const pollen = air.pollen && typeof air.pollen === "object" ? air.pollen : {};
        const kinds = Object.keys(POLLEN_NAMES)
            .filter((kind) => typeof pollen[kind] === "number" && pollen[kind] >= 1)
            .sort((a, b) => pollen[b] - pollen[a])
            .slice(0, 2)
            .map((kind) => `${POLLEN_NAMES[kind]} ${Math.round(pollen[kind])}`);
        if (kinds.length) parts.push(`Pollen: ${kinds.join(", ")}`);
        return { value: band ? `${index} ${band}` : String(index), note: parts.join(" · ") };
    }

    // Names of the sources to credit, once each: weather, values filled from a second source, alerts,
    // then air quality
    function sourceText(weather) {
        const sources = (weather && weather.sources) || {};
        const names = [];
        for (const entry of [sources.weather, sources.fill, sources.alerts, sources.air_quality]) {
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
    // cover only the countries on the WMO alert hub, OpenWeatherMap's only the services that send it
    // theirs), so "none" is said as "none reported by" them
    const UNCERTAIN_ALERTS_SOURCES = ["pirateweather", "openweathermap"];

    // The name to give in "none reported by ...", or "" when an empty list really means no alerts
    function uncertainAlertsSource(weather) {
        const source = weather && weather.sources && weather.sources.alerts;
        if (!source || !UNCERTAIN_ALERTS_SOURCES.includes(source.id)) return "";
        return typeof source.name === "string" && source.name.trim() ? source.name.trim() : source.id;
    }

    const api = {
        SCHEMA_VERSION, DEFAULT_UNITS, OLD_READING_MS, WEATHER_URLS, units, sourceText, alertsSupported,
        uncertainAlertsSource, alertTime, airQualityText, gustText, amountText, compass, windText, dewPointText, oldReadingTime, fetchWeather, apiError,
    };

    root.OutpostData = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
