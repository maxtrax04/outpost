// Outpost clock: 12- or 24-hour times on every theme.
// Sets data-clock="auto", "12", or "24" on <html>; app.js formats times with time() and dateTime(),
// in the weather location's time zone (setZone), labelled when it differs from the viewer's.
//
// Which setting is used, in order:
//   1. ?clock=12 or ?clock=24 in the address (?clock=auto for the browser's own)
//   2. the choice saved in this browser with the "24-hour clock" checkbox in the theme panel
//      (ignored when the server hides it: OUTPOST_CLOCK_TOGGLE=false)
//   3. OUTPOST_CLOCK on the server (data/config.json ui.clock)
//   4. auto: the browser's language decides. Browsers do not share the device's 12/24-hour
//      clock setting with pages, so a browser in US English shows 12-hour times.

(function (root) {
    "use strict";

    const STORAGE_KEY = "outpost.clock";
    const ALIASES = { "12": "12", "12h": "12", "24": "24", "24h": "24", "auto": "auto" };

    // Used when browser storage is blocked, so a choice still lasts until the page is reloaded
    let sessionChoice = null;
    let lastConfig = {};
    let current = "auto";

    function pick(value) {
        return ALIASES[String(value || "").trim().toLowerCase()] || null;
    }

    // A saved choice is always 12 or 24 (the checkbox has no "auto"; "Use server default" clears it)
    function validSaved(value) {
        return value === "12" || value === "24" ? value : null;
    }

    function toggleAllowed(config) {
        return !(config && config.ui && config.ui.clock_toggle === false);
    }

    // Browser storage can be blocked (private browsing, kiosk policies), so never assume it works
    function readSaved(storage) {
        try {
            return validSaved((storage || root.localStorage).getItem(STORAGE_KEY));
        } catch (error) {
            return null;
        }
    }

    function writeSaved(value, storage) {
        try {
            const target = storage || root.localStorage;
            if (value) {
                target.setItem(STORAGE_KEY, value);
            } else {
                target.removeItem(STORAGE_KEY);
            }
            return true;
        } catch (error) {
            return false;
        }
    }

    function choose(config, search, storage) {
        const fromAddress = pick(new URLSearchParams(search || "").get("clock"));
        const saved = toggleAllowed(config) ? (readSaved(storage) || sessionChoice) : null;
        const server = pick(config && config.ui && config.ui.clock) || "auto";
        return { clock: fromAddress || saved || server, fromAddress, saved, server };
    }

    // Extra toLocale*String options for a choice. hourCycle (not hour12) so midnight is
    // 00:05 in 24-hour time, never 24:05; 24-hour times always have two-digit hours (04:02).
    function options(choice) {
        if (choice === "12") return { hourCycle: "h12" };
        if (choice === "24") return { hourCycle: "h23", hour: "2-digit" };
        return {};
    }

    // What "auto" means in this browser (or for the given languages): "12" or "24"
    function browserDefault(locales = []) {
        const cycle = new Intl.DateTimeFormat(locales, { hour: "numeric" }).resolvedOptions().hourCycle;
        return cycle === "h23" || cycle === "h24" ? "24" : "12";
    }

    // The clock actually shown: "12" or "24"
    function effective(choice = current, locales = []) {
        return choice === "auto" ? browserDefault(locales) : choice;
    }

    // ---- The location's time zone --------------------------------------------------------------
    // Times are shown as they are at the weather location (weather.json "timezone"), so a dashboard
    // for a faraway place shows its sunrise in that place's time. When that differs from the viewer's
    // own time zone, the zone's short name is added ("4:12 PM GMT+1"), so it is clear whose time it is.

    let zone = null;

    // An IANA name this browser knows, such as "Europe/Oslo", or null
    function validZone(name) {
        if (typeof name !== "string" || !name.trim()) return null;
        try {
            new Intl.DateTimeFormat("en-US", { timeZone: name.trim() });
            return name.trim();
        } catch (error) {
            return null;
        }
    }

    // Sets the location's time zone (null or unknown: the viewer's own); returns what is used
    function setZone(name) {
        zone = validZone(name);
        return zone;
    }

    function getZone() {
        return zone;
    }

    // The UTC offset of a time zone at a moment, as "GMT+01:00" (undefined: the viewer's own)
    function offsetAt(date, timeZone) {
        try {
            const parts = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "longOffset" }).formatToParts(date);
            const part = parts.find((item) => item.type === "timeZoneName");
            return part ? part.value : null;
        } catch (error) {
            return null;  // an older browser: no label rather than a wrong one
        }
    }

    // True when the location's clock shows a different time than the viewer's at that moment
    function differs(date, timeZone = zone) {
        if (!timeZone) return false;
        const there = offsetAt(date, timeZone);
        return there !== null && there !== offsetAt(date, undefined);
    }

    // Extra toLocale*String options for showing a moment in the location's time
    function zoneOptions(date, timeZone = zone, label = true) {
        if (!timeZone) return {};
        return label && differs(date, timeZone) ? { timeZone, timeZoneName: "short" } : { timeZone };
    }

    function time(date, choice = current, locales = [], timeZone = zone) {
        return date.toLocaleTimeString(locales, {
            hour: "numeric", minute: "2-digit", ...options(choice), ...zoneOptions(date, timeZone)
        });
    }

    function dateTime(date, choice = current, locales = [], timeZone = zone) {
        return date.toLocaleString(locales, {
            month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...options(choice),
            ...zoneOptions(date, timeZone)
        });
    }

    // A date (no time) as it is at the location, for example for the subtitle's {date}
    function day(date, format, locales = [], timeZone = zone) {
        return date.toLocaleDateString(locales, { ...format, ...zoneOptions(date, timeZone, false) });
    }

    // Applies the setting to the page; returns what choose() decided
    function apply(config) {
        lastConfig = config || {};
        const choice = choose(lastConfig, root.location.search);
        current = choice.clock;
        root.document.documentElement.dataset.clock = current;
        return choice;
    }

    function savedChoice() {
        return choose(lastConfig, "").saved;
    }

    function removeFromAddress() {
        const url = new URL(root.location.href);
        if (url.searchParams.has("clock")) {
            url.searchParams.delete("clock");
            root.history.replaceState(null, "", url.toString());
        }
    }

    // The viewer's checkbox: switches between 12- and 24-hour and remembers it in this browser.
    // Returns false when the browser blocks saving (the choice then lasts until a reload).
    function toggle() {
        const value = effective() === "24" ? "12" : "24";
        const stored = writeSaved(value);
        sessionChoice = stored ? null : value;
        removeFromAddress();
        apply(lastConfig);
        return stored;
    }

    // Forgets the viewer's choice, back to the server setting
    function clear() {
        writeSaved(null);
        sessionChoice = null;
        removeFromAddress();
        apply(lastConfig);
    }

    const api = {
        STORAGE_KEY, pick, toggleAllowed, readSaved, writeSaved, choose, options, browserDefault,
        effective, time, dateTime, day, apply, savedChoice, toggle, clear,
        validZone, setZone, getZone, offsetAt, differs, zoneOptions,
    };

    root.OutpostClock = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
