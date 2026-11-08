// Outpost reduced effects: no scanlines, glow, or animation, in every theme.
// Sets data-effects="full" or "reduced" on <html>; style.css (and any theme) does the rest.
//
// Which setting is used, in order:
//   1. ?effects=reduced or ?effects=full in the address
//   2. the choice saved in this browser with the toggle in the theme panel
//      (ignored when the server hides the toggle: OUTPOST_EFFECTS_TOGGLE=false)
//   3. reduced, when the server says so (OUTPOST_EFFECTS=reduced) or the device asks for
//      reduced motion
//   4. full

(function (root) {
    "use strict";

    const STORAGE_KEY = "outpost.effects";
    const VALUES = ["full", "reduced"];
    const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

    // Used when browser storage is blocked, so a choice still lasts until the page is reloaded
    let sessionChoice = null;
    let lastConfig = {};
    let watchingDevice = false;

    function valid(value) {
        return VALUES.includes(value) ? value : null;
    }

    function toggleAllowed(config) {
        return !(config && config.ui && config.ui.effects_toggle === false);
    }

    // Browser storage can be blocked (private browsing, kiosk policies), so never assume it works
    function readSaved(storage) {
        try {
            return valid((storage || root.localStorage).getItem(STORAGE_KEY));
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

    function deviceWantsReduced() {
        try {
            return root.matchMedia(REDUCED_MOTION).matches;
        } catch (error) {
            return false;
        }
    }

    function choose(config, search, storage, deviceReduced) {
        const fromAddress = valid(new URLSearchParams(search || "").get("effects"));
        const saved = toggleAllowed(config) ? (readSaved(storage) || sessionChoice) : null;
        const server = valid(config && config.ui && config.ui.effects) || "full";
        const automatic = server === "reduced" || deviceReduced ? "reduced" : "full";
        return { effects: fromAddress || saved || automatic, fromAddress, saved, automatic };
    }

    // Applies the setting to the page; returns what choose() decided
    function apply(config) {
        lastConfig = config || {};
        const choice = choose(lastConfig, root.location.search, undefined, deviceWantsReduced());
        root.document.documentElement.dataset.effects = choice.effects;

        if (!watchingDevice && typeof root.matchMedia === "function") {
            // Follow the device setting if it changes while the page is open
            root.matchMedia(REDUCED_MOTION).addEventListener("change", () => apply(lastConfig));
            watchingDevice = true;
        }
        return choice;
    }

    function current() {
        return root.document.documentElement.dataset.effects === "reduced" ? "reduced" : "full";
    }

    function savedChoice() {
        return choose(lastConfig, "", undefined, false).saved;
    }

    function removeFromAddress() {
        const url = new URL(root.location.href);
        if (url.searchParams.has("effects")) {
            url.searchParams.delete("effects");
            root.history.replaceState(null, "", url.toString());
        }
    }

    // The viewer's toggle: switches between full and reduced and remembers it in this browser.
    // Returns false when the browser blocks saving (the choice then lasts until a reload).
    function toggle() {
        const value = current() === "reduced" ? "full" : "reduced";
        const stored = writeSaved(value);
        sessionChoice = stored ? null : value;
        removeFromAddress();
        apply(lastConfig);
        return stored;
    }

    // Forgets the viewer's choice, back to the server and device setting
    function clear() {
        writeSaved(null);
        sessionChoice = null;
        removeFromAddress();
        apply(lastConfig);
    }

    const api = { STORAGE_KEY, valid, toggleAllowed, readSaved, writeSaved, choose, apply, current, savedChoice, toggle, clear };

    root.OutpostEffects = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
