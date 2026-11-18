// The LOCATION part of the options panel (index.html #placeSection): home, the places chosen before,
// "Use my location", and the search box. Shown only when the server has location search on (/api/status).
// The choices themselves are kept by places.js; app.js shows the chosen place's weather.

(function (root) {
    "use strict";

    // The search runs when the viewer presses Enter or stops typing for this long, not on every key
    const SEARCH_PAUSE_MS = 700;
    const BLOCKED_NOTE = "This browser blocks saving; the choice lasts until you reload.";
    const PRIVACY_NOTE = "Places are kept in this browser. Searches are sent to Open-Meteo.";

    let searchOn = false;
    let homeName = "";
    let wired = false;
    let timer = null;
    let searchNumber = 0;
    let lastSearched = "";

    const byId = (id) => document.getElementById(id);

    function note(text) {
        byId("placeNote").textContent = text || PRIVACY_NOTE;
    }

    // Called by app.js on every refresh
    function configure(options) {
        searchOn = Boolean(options && options.on);
        if (options && options.homeName) homeName = options.homeName;
        if (!byId("themePanel").hidden) build();
        else byId("placeSection").hidden = !searchOn;
    }

    function clearResults() {
        byId("placeResults").replaceChildren();
        lastSearched = "";
    }

    async function select(place) {
        const stored = OutpostPlaces.choose(place);
        OutpostPlaces.removeFromAddress();
        clearResults();
        byId("placeQuery").value = "";
        build();
        note(stored ? "" : BLOCKED_NOTE);
        await root.refresh();
    }

    async function forget(place) {
        const { place: shown } = OutpostPlaces.current(undefined, undefined, searchOn);
        const stored = OutpostPlaces.forget(place);
        build();
        note(stored ? "" : BLOCKED_NOTE);
        if (shown && OutpostPlaces.samePlace(shown, place)) await root.refresh();
    }

    function row(place, label, checked, forgettable) {
        const wrap = document.createElement("div");
        wrap.className = "place-row";

        const option = document.createElement("button");
        option.type = "button";
        option.className = "theme-option place-option";
        option.setAttribute("role", "radio");
        option.setAttribute("aria-checked", String(checked));
        option.textContent = label;
        option.addEventListener("click", () => select(place));
        wrap.appendChild(option);

        if (forgettable) {
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "place-forget";
            remove.textContent = "x";
            remove.setAttribute("aria-label", `Forget ${label}`);
            remove.title = "Forget this place";
            remove.addEventListener("click", () => forget(place));
            wrap.appendChild(remove);
        }
        return wrap;
    }

    // Draws home and the saved places; leaves the search box and its results alone
    function build() {
        const section = byId("placeSection");
        section.hidden = !searchOn;
        if (!searchOn) return;
        wire();

        const { place: shown, pinned } = OutpostPlaces.current(undefined, undefined, true);
        const saved = OutpostPlaces.savedPlaces();
        const list = byId("placeList");
        list.replaceChildren(row(null, homeName ? `Home (${homeName})` : "Home", shown === null, false));

        // A place from the address that is not saved: shown, and saved if the viewer chooses it
        if (pinned && !saved.some((place) => OutpostPlaces.samePlace(place, shown))) {
            list.appendChild(row(shown, `${shown.name} (from the address)`, true, false));
        }
        for (const place of saved) {
            list.appendChild(row(place, place.name, Boolean(shown) && OutpostPlaces.samePlace(place, shown), true));
        }

        // My location: only where the browser has it at all. Over plain HTTP the browser refuses, so
        // the button says so up front, and a tap explains.
        const mine = byId("myLocation");
        mine.hidden = !("geolocation" in navigator);
        mine.textContent = root.isSecureContext ? "Use my location" : "Use my location (needs HTTPS)";

        if (!byId("placeNote").textContent) note("");
    }

    function useMyLocation() {
        const button = byId("myLocation");
        if (!root.isSecureContext || !("geolocation" in navigator)) {
            note(OutpostPlaces.locationProblem(null, root.isSecureContext));
            return;
        }
        button.disabled = true;
        note("Asking the browser for this device's location...");
        navigator.geolocation.getCurrentPosition(
            (position) => {
                button.disabled = false;
                const place = OutpostPlaces.fromPosition(position);
                if (place) select(place);
                else note(OutpostPlaces.locationProblem(null, true));
            },
            (error) => {
                button.disabled = false;
                note(OutpostPlaces.locationProblem(error, true));
            },
            OutpostPlaces.GEOLOCATION_OPTIONS
        );
    }

    function showResults(places, text) {
        const results = byId("placeResults");
        results.replaceChildren();
        for (const result of places) {
            const place = OutpostPlaces.validPlace({ ...result, name: OutpostPlaces.resultName(result) });
            if (!place) continue;
            const item = document.createElement("div");
            item.setAttribute("role", "listitem");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "theme-option place-result";
            button.textContent = OutpostPlaces.resultDetail(result);
            button.addEventListener("click", () => select(place));
            item.appendChild(button);
            results.appendChild(item);
        }
        note(results.children.length ? "Choose a place:" : `No places found for "${text}".`);
    }

    async function search(force) {
        clearTimeout(timer);
        const text = byId("placeQuery").value.replace(/\s+/g, " ").trim();
        if (text.length < 2) {
            clearResults();
            note(text ? "Type at least 2 letters." : "");
            return;
        }
        if (text === lastSearched && !force) return;
        lastSearched = text;
        const number = ++searchNumber;
        note("Searching...");
        try {
            const response = await fetch(OutpostPlaces.searchUrl(text));
            if (!response.ok) throw await OutpostData.apiError(response);
            const body = await response.json();
            if (number !== searchNumber) return; // a newer search has started
            showResults(Array.isArray(body.places) ? body.places : [], text);
        } catch (error) {
            if (number !== searchNumber) return;
            byId("placeResults").replaceChildren();
            lastSearched = "";
            note(error.apiMessage || "Search is not available right now; try again later.");
        }
    }

    function wire() {
        if (wired) return;
        wired = true;
        byId("placeSearch").addEventListener("submit", (event) => {
            event.preventDefault();
            search(true);
        });
        byId("myLocation").addEventListener("click", useMyLocation);
        byId("placeQuery").addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(() => search(false), SEARCH_PAUSE_MS);
        });
    }

    root.OutpostPlacePanel = { configure, build };
})(window);
