// The place a screen shows: home (the server's OUTPOST_LATITUDE/LONGITUDE) or another place the
// viewer chose with the location search (docs/api-design.md). Choices are kept in this browser only.
//
// Which place is shown, in order:
//   1. ?lat=..&lon=..&name=.. in the address (pins one screen to a place)
//   2. the place chosen in this browser, while the server allows location search
//   3. home
// Kept apart from app.js so it can be tested without a page.

(function (root) {
    "use strict";

    const CHOICE_KEY = "outpost.place";     // the chosen place; nothing means home
    const SAVED_KEY = "outpost.places";     // places chosen before, most recent first
    const MAX_SAVED = 10;
    const MAX_NAME_LENGTH = 80;             // the server's limit too (outpost_server.py)
    const DEFAULT_NAME = "Selected location";

    // Used when browser storage is blocked, so a choice still lasts until the page is reloaded
    let session = { choice: undefined, saved: undefined };

    // Plain text on one line, at most MAX_NAME_LENGTH characters
    function cleanName(text) {
        return String(text === undefined || text === null ? "" : text)
            .replace(/[\u0000-\u001f\u007f]+/g, " ")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, MAX_NAME_LENGTH)
            .trim();
    }

    function number(value, limit) {
        if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) return null;
        const result = Number(value);
        return Number.isFinite(result) && Math.abs(result) <= limit ? result : null;
    }

    // Coordinates are kept to 2 decimals (about 1 km), as the server rounds them: no more exact a
    // place than that is stored in the browser or sent anywhere (+ 0 turns -0 into 0)
    const round = (value) => Math.round(value * 100) / 100 + 0;

    // { name, latitude, longitude } from anything that looks like a place, or null
    function validPlace(value) {
        if (!value || typeof value !== "object") return null;
        const latitude = number(value.latitude, 90);
        const longitude = number(value.longitude, 180);
        if (latitude === null || longitude === null) return null;
        return { name: cleanName(value.name) || DEFAULT_NAME, latitude: round(latitude), longitude: round(longitude) };
    }

    // Places within about 1 km are the same place: the server rounds coordinates to 2 decimals
    function key(place) {
        return place ? `${place.latitude.toFixed(2)},${place.longitude.toFixed(2)}` : "home";
    }

    function samePlace(a, b) {
        return key(a) === key(b);
    }

    // The name to show for a search result: "Cinder Flats, North Province", or with the country
    // when there is no region
    function resultName(result) {
        const name = cleanName(result && result.name);
        const extra = cleanName((result && (result.region || result.country)) || "");
        return cleanName(extra && extra !== name ? `${name}, ${extra}` : name);
    }

    // The longer line in the search results: name, region, and country
    function resultDetail(result) {
        const parts = [];
        for (const part of [result && result.name, result && result.region, result && result.country]) {
            const text = cleanName(part);
            if (text && !parts.includes(text)) parts.push(text);
        }
        return parts.join(", ");
    }

    // The place pinned in the address, or null
    function fromAddress(search) {
        const params = new URLSearchParams(search !== undefined ? search : root.location.search);
        if (!params.has("lat") && !params.has("lon")) return null;
        return validPlace({ latitude: params.get("lat"), longitude: params.get("lon"), name: params.get("name") });
    }

    // Browser storage can be blocked (private browsing, kiosk policies), so never assume it works
    function read(storage, name) {
        try {
            const text = (storage || root.localStorage).getItem(name);
            return text ? JSON.parse(text) : null;
        } catch (error) {
            return null;
        }
    }

    function write(storage, name, value) {
        try {
            const target = storage || root.localStorage;
            if (value === null) {
                target.removeItem(name);
            } else {
                target.setItem(name, JSON.stringify(value));
            }
            return true;
        } catch (error) {
            return false;
        }
    }

    function savedPlaces(storage) {
        const list = session.saved !== undefined ? session.saved : read(storage, SAVED_KEY);
        const places = [];
        for (const item of Array.isArray(list) ? list : []) {
            const place = validPlace(item);
            if (place && !places.some((other) => samePlace(other, place))) places.push(place);
        }
        return places.slice(0, MAX_SAVED);
    }

    function savedChoice(storage) {
        return validPlace(session.choice !== undefined ? session.choice : read(storage, CHOICE_KEY));
    }

    // Makes place (or home, for null) the choice in this browser. A place goes to the top of the
    // saved list. Returns false when the browser blocks saving (the choice then lasts until a reload).
    function choose(place, storage) {
        const chosen = validPlace(place);
        let stored = write(storage, CHOICE_KEY, chosen);
        let list = savedPlaces(storage);
        if (chosen) {
            // One entry per place, and one "My location" (the latest position replaces the last)
            const replaced = (other) => samePlace(other, chosen) || (isMyLocation(chosen) && isMyLocation(other));
            list = [chosen].concat(list.filter((other) => !replaced(other))).slice(0, MAX_SAVED);
            stored = write(storage, SAVED_KEY, list) && stored;
        }
        session = stored ? { choice: undefined, saved: undefined } : { choice: chosen, saved: list };
        return stored;
    }

    // Removes a place from the saved list; if it was the choice, home is shown again
    function forget(place, storage) {
        const list = savedPlaces(storage).filter((other) => !samePlace(other, place));
        const choice = savedChoice(storage);
        const nextChoice = choice && samePlace(choice, place) ? null : choice;
        const stored = write(storage, SAVED_KEY, list) && write(storage, CHOICE_KEY, nextChoice);
        session = stored ? { choice: undefined, saved: undefined } : { choice: nextChoice, saved: list };
        return stored;
    }

    // What to show: { place (null for home), pinned (true when it comes from the address) }.
    // searchOn is false when the server has location search turned off: a saved choice is then
    // set aside (not forgotten), but a pinned place is still asked for, and the server refuses it.
    function current(search, storage, searchOn) {
        const pinned = fromAddress(search);
        if (pinned) return { place: pinned, pinned: true };
        return { place: searchOn === false ? null : savedChoice(storage), pinned: false };
    }

    // The address of the chosen place's weather, relative so it also works under a path prefix
    function weatherUrl(place) {
        if (!place) return "api/weather";
        const params = new URLSearchParams({ lat: String(place.latitude), lon: String(place.longitude), name: place.name });
        return `api/weather?${params.toString()}`;
    }

    function searchUrl(text) {
        return `api/places?${new URLSearchParams({ q: text }).toString()}`;
    }

    // Takes the pinned place out of the address once the viewer chooses another
    function removeFromAddress(win) {
        const target = win || root;
        const url = new URL(target.location.href);
        let changed = false;
        for (const name of ["lat", "lon", "name"]) {
            if (url.searchParams.has(name)) {
                url.searchParams.delete(name);
                changed = true;
            }
        }
        if (changed) target.history.replaceState(null, "", url.toString());
        return changed;
    }

    // ---- My location (#31) ----
    // The browser's position becomes a place like any search result, rounded to about 1 km, so no
    // more exact a position is stored or sent. It is asked for once per tap, never watched.
    const MY_LOCATION_NAME = "My location";
    const GEOLOCATION_OPTIONS = { enableHighAccuracy: false, timeout: 15000, maximumAge: 10 * 60 * 1000 };

    function fromPosition(position) {
        const coords = position && position.coords;
        return coords ? validPlace({ name: MY_LOCATION_NAME, latitude: coords.latitude, longitude: coords.longitude }) : null;
    }

    function isMyLocation(place) {
        return Boolean(place) && place.name === MY_LOCATION_NAME;
    }

    // Why the location could not be used, for the panel. secure is window.isSecureContext: browsers
    // share their location only with HTTPS pages (and localhost).
    function locationProblem(error, secure) {
        if (secure === false) {
            return "Browsers share their location only with HTTPS pages. Search for a place instead.";
        }
        switch (error && error.code) {
            case 1: // PERMISSION_DENIED (also inside a frame that is not allowed to ask)
                return "Location is blocked for this page. Allow it in the browser's site settings, or search for a place.";
            case 2: // POSITION_UNAVAILABLE
                return "This device could not find its location. Search for a place instead.";
            case 3: // TIMEOUT
                return "Finding the location took too long. Try again, or search for a place.";
            default:
                return "This browser cannot share its location. Search for a place instead.";
        }
    }

    // Only for tests: forget a choice kept because storage was blocked
    function resetSession() {
        session = { choice: undefined, saved: undefined };
    }

    const api = {
        CHOICE_KEY, SAVED_KEY, MAX_SAVED, MAX_NAME_LENGTH, DEFAULT_NAME, cleanName, validPlace, key, samePlace,
        resultName, resultDetail, fromAddress, savedPlaces, savedChoice, choose, forget, current, weatherUrl,
        searchUrl, removeFromAddress, resetSession, MY_LOCATION_NAME, GEOLOCATION_OPTIONS, fromPosition,
        isMyLocation, locationProblem,
    };

    root.OutpostPlaces = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
