// Outpost day/night dimming.
// Works out how bright the display should be from the sun's position at the
// configured coordinates (no network needed), or from a fixed nightly schedule.
// Brightness runs from 1 (full) down to the configured night level.

(function (root) {
    "use strict";

    const RAD = Math.PI / 180;
    const DEFAULT_LEVEL = 0.35;
    const MIN_LEVEL = 0.05;

    // Sun elevation (degrees) where dimming starts and finishes.
    // 0 = sunset/sunrise; -6 = end of civil twilight (about 30 minutes later).
    const FULL_DAY_ELEVATION = 0;
    const FULL_NIGHT_ELEVATION = -6;

    // Schedule mode: how long the fade takes, in minutes.
    const SCHEDULE_RAMP_MINUTES = 30;

    const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
    const mod = (value, size) => ((value % size) + size) % size;

    // Latitude and longitude from the settings as numbers, or null if they are missing or invalid.
    // Number(null) and Number("") are both 0, which would silently mean "the Gulf of Guinea",
    // so empty values are rejected explicitly.
    function coordinates(config) {
        const read = (value) =>
            value === null || value === undefined || (typeof value === "string" && value.trim() === "")
                ? NaN
                : Number(value);

        const latitude = read(config && config.latitude);
        const longitude = read(config && config.longitude);

        if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
            return null;
        }
        return { latitude, longitude };
    }

    // Sun elevation above the horizon in degrees (low-precision Astronomical
    // Almanac formulas, accurate to a small fraction of a degree).
    function solarElevation(date, latitude, longitude) {
        const julianDay = date.getTime() / 86400000 + 2440587.5;
        const n = julianDay - 2451545.0;

        const meanLongitude = mod(280.460 + 0.9856474 * n, 360);
        const meanAnomaly = mod(357.528 + 0.9856003 * n, 360) * RAD;
        const eclipticLongitude =
            (meanLongitude + 1.915 * Math.sin(meanAnomaly) + 0.020 * Math.sin(2 * meanAnomaly)) * RAD;
        const obliquity = (23.439 - 0.0000004 * n) * RAD;

        const declination = Math.asin(Math.sin(obliquity) * Math.sin(eclipticLongitude));
        const rightAscension = Math.atan2(
            Math.cos(obliquity) * Math.sin(eclipticLongitude),
            Math.cos(eclipticLongitude)
        );

        const siderealTime = mod(280.46061837 + 360.98564736629 * n + longitude, 360) * RAD;
        const hourAngle = siderealTime - rightAscension;
        const lat = latitude * RAD;

        const sinElevation =
            Math.sin(lat) * Math.sin(declination) +
            Math.cos(lat) * Math.cos(declination) * Math.cos(hourAngle);

        return Math.asin(clamp(sinElevation, -1, 1)) / RAD;
    }

    // ---- Sunrise and sunset ----------------------------------------------
    // The sun's upper edge touching the horizon, allowing for atmospheric refraction.
    const SUN_EDGE_ELEVATION = -0.833;
    const SCAN_STEP_MS = 10 * 60000;

    // Sunrise and sunset around the local calendar day of `date` (in the viewer's
    // time zone). Returns { sunrise, sunset, polar }: Dates (or null when the sun is
    // already up or does not set that day), and polar = "day" or "night" when the
    // sun never crosses the horizon. Returns null if the coordinates are missing.
    function sunTimes(date, latitude, longitude) {
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
            return null;
        }

        const start = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
        const dayEnd = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1).getTime();
        const scanEnd = start + 48 * 3600000;

        const height = (time) => solarElevation(new Date(time), latitude, longitude) - SUN_EDGE_ELEVATION;

        // Narrow a crossing found between two scan points down to about a second
        const refine = (low, high, rising) => {
            while (high - low > 1000) {
                const middle = (low + high) / 2;
                const up = height(middle) > 0;
                if (up === rising) {
                    high = middle;
                } else {
                    low = middle;
                }
            }
            return high;
        };

        const crossings = [];
        let previousTime = start;
        let previousHeight = height(start);
        for (let time = start + SCAN_STEP_MS; time <= scanEnd; time += SCAN_STEP_MS) {
            const currentHeight = height(time);
            if (previousHeight <= 0 && currentHeight > 0) {
                crossings.push({ time: refine(previousTime, time, true), rising: true });
            } else if (previousHeight > 0 && currentHeight <= 0) {
                crossings.push({ time: refine(previousTime, time, false), rising: false });
            }
            previousTime = time;
            previousHeight = currentHeight;
        }

        if (crossings.length === 0) {
            return { sunrise: null, sunset: null, polar: height(start) > 0 ? "day" : "night" };
        }

        const rise = crossings.find((c) => c.rising && c.time < dayEnd);
        const set = rise
            ? crossings.find((c) => !c.rising && c.time > rise.time)
            : crossings.find((c) => !c.rising && c.time < dayEnd);

        return {
            sunrise: rise ? new Date(rise.time) : null,
            sunset: set ? new Date(set.time) : null,
            polar: null,
        };
    }

    // "22:30" -> 1350 (minutes after midnight), or null if invalid
    function parseTime(text) {
        const match = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(String(text || "").trim());
        return match ? Number(match[1]) * 60 + Number(match[2]) : null;
    }

    // 0 = full day, 1 = full night
    function nightnessFromSun(date, latitude, longitude) {
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
            return 0;
        }
        const elevation = solarElevation(date, latitude, longitude);
        const day = clamp(
            (elevation - FULL_NIGHT_ELEVATION) / (FULL_DAY_ELEVATION - FULL_NIGHT_ELEVATION),
            0,
            1
        );
        const smooth = day * day * (3 - 2 * day);
        return 1 - smooth;
    }

    // Night window from start to end (may cross midnight). Fades in over the
    // ramp after start, and fades out over the ramp after end.
    function nightnessFromSchedule(date, start, end) {
        const startMinute = parseTime(start);
        const endMinute = parseTime(end);
        if (startMinute === null || endMinute === null || startMinute === endMinute) {
            return 0;
        }

        const minutes = date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60;
        const windowLength = mod(endMinute - startMinute, 1440);
        const intoWindow = mod(minutes - startMinute, 1440);

        if (intoWindow < windowLength) {
            return clamp(intoWindow / SCHEDULE_RAMP_MINUTES, 0, 1);
        }

        const sinceEnd = intoWindow - windowLength;
        if (sinceEnd < SCHEDULE_RAMP_MINUTES) {
            return 1 - sinceEnd / SCHEDULE_RAMP_MINUTES;
        }

        return 0;
    }

    // config comes from data/config.json:
    // { latitude, longitude, dim: { enabled, level, mode, start, end } }
    function brightness(config, date) {
        const dim = (config && config.dim) || {};
        if (dim.enabled === false) {
            return 1;
        }

        const level = clamp(Number.isFinite(Number(dim.level)) ? Number(dim.level) : DEFAULT_LEVEL, MIN_LEVEL, 1);
        const now = date || new Date();

        let nightness;
        if (dim.mode === "schedule") {
            nightness = nightnessFromSchedule(now, dim.start, dim.end);
        } else {
            const place = coordinates(config);
            nightness = place ? nightnessFromSun(now, place.latitude, place.longitude) : 0;
        }

        return 1 - nightness * (1 - level);
    }

    const api = { coordinates, solarElevation, sunTimes, brightness, parseTime, DEFAULT_LEVEL };
    root.OutpostDim = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
