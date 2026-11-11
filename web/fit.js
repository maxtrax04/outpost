// Outpost fit to screen: shrinks the whole dashboard just enough that it fits the screen without
// scrolling. For wall displays and for themes that frame the page like a single screen.
//
// A theme turns it on with `--fit-screen: 1` in its :root. For testing any theme, add ?fit=on
// (or ?fit=off) to the address. When it is on, <html> gets data-fit="on" and style.css scales
// <main> by --fit-scale.
//
// It never shrinks below MIN_SCALE: if the page would need more than that (a phone in portrait,
// say), it is left at full size and scrolls as usual, because tiny text is worse than scrolling.
//
// A theme can also let it grow on big screens, so the page fills them: `--fit-max-scale: 2`
// allows up to twice the normal size. The default is 1 (shrink only).

(function (root) {
    "use strict";

    const MIN_SCALE = 0.55;
    const STEPS = 8; // binary search steps: precise to about 0.2%

    let scheduled = false;
    let listening = false;

    // Whether fitting is wanted: the address wins, then the theme's --fit-screen
    function wanted(search, themeValue) {
        const fromAddress = new URLSearchParams(search || "").get("fit");
        if (fromAddress === "on") return true;
        if (fromAddress === "off") return false;
        return String(themeValue || "").trim() === "1";
    }

    // How large the theme lets the page grow: its --fit-max-scale, from 1 (the default) to 4
    function maxScale(themeValue) {
        const value = parseFloat(String(themeValue || "").trim());
        return Number.isFinite(value) ? Math.min(4, Math.max(1, value)) : 1;
    }

    // The largest scale in [minScale, maxScale] at which fits(scale) is true, or null if even
    // minScale does not fit. fits() must get easier as the scale gets smaller.
    function chooseScale(fits, minScale = MIN_SCALE, largest = 1, steps = STEPS) {
        if (fits(largest)) return largest;
        if (!fits(minScale)) return null;
        let low = minScale;  // fits
        let high = largest;  // does not fit
        for (let i = 0; i < steps; i++) {
            const middle = (low + high) / 2;
            if (fits(middle)) low = middle; else high = middle;
        }
        return Math.floor(low * 1000) / 1000;
    }

    function setScale(html, scale) {
        html.style.setProperty("--fit-scale", String(scale));
    }

    // Measures the page and sets the scale. Returns the scale used, or null when not fitting.
    function apply() {
        const doc = root.document;
        const html = doc.documentElement;
        const main = doc.querySelector("main");
        const themeValue = root.getComputedStyle(html).getPropertyValue("--fit-screen");

        if (!main || !wanted(root.location.search, themeValue)) {
            delete html.dataset.fit;
            html.style.removeProperty("--fit-scale");
            return null;
        }

        html.dataset.fit = "on";
        const available = root.innerHeight;
        const fits = (scale) => {
            setScale(html, scale);
            return main.getBoundingClientRect().height <= available + 0.5;
        };
        const largest = maxScale(root.getComputedStyle(html).getPropertyValue("--fit-max-scale"));
        const scale = chooseScale(fits, MIN_SCALE, largest, STEPS + Math.ceil(Math.log2(largest)));

        if (scale === null) {
            // Too much to fit at a readable size: show it full size and let it scroll
            delete html.dataset.fit;
            html.style.removeProperty("--fit-scale");
            return null;
        }
        setScale(html, scale);
        return scale;
    }

    // Fits again on the next frame (several changes in a row are measured once)
    function schedule() {
        if (scheduled) return;
        scheduled = true;
        root.requestAnimationFrame(() => {
            scheduled = false;
            apply();
        });
    }

    // Starts fitting: now, when the window changes size, and when web fonts finish loading.
    // The page also calls schedule() after it renders new data or switches theme.
    function start() {
        if (!listening) {
            listening = true;
            root.addEventListener("resize", schedule);
            if (root.document.fonts && root.document.fonts.addEventListener) {
                root.document.fonts.addEventListener("loadingdone", schedule);
            }
        }
        schedule();
    }

    const api = { MIN_SCALE, wanted, maxScale, chooseScale, apply, schedule, start };

    root.OutpostFit = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
