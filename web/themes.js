// Outpost themes: choosing the theme, remembering a viewer's choice, and the on-screen switcher.
//
// Which theme is used, in order:
//   1. ?theme=name in the address (handy for previews)
//   2. the choice saved in this browser (from the on-screen switcher)
//   3. OUTPOST_THEME on the server (from data/config.json)
//   4. the default

const DEFAULT_THEME = "retro-crt";
const THEME_STORAGE_KEY = "outpost.theme";

// Used when browser storage is blocked, so a choice still lasts until the page is reloaded
let sessionTheme = null;

function validTheme(name) {
    return typeof name === "string" && /^[a-z0-9-]+$/.test(name) ? name : null;
}

// Browser storage can be blocked (private browsing, kiosk policies), so never assume it works.
function readSavedTheme(storage) {
    try {
        return validTheme((storage || window.localStorage).getItem(THEME_STORAGE_KEY));
    } catch (error) {
        return null;
    }
}

function writeSavedTheme(name, storage) {
    try {
        const target = storage || window.localStorage;
        if (name) {
            target.setItem(THEME_STORAGE_KEY, name);
        } else {
            target.removeItem(THEME_STORAGE_KEY);
        }
        return true;
    } catch (error) {
        return false;
    }
}

// The themes the server found, as [{ id, name }]
function availableThemes(config) {
    const list = config && Array.isArray(config.themes) ? config.themes : [];
    return list
        .map((theme) => ({
            id: validTheme(theme && theme.id),
            name: String((theme && (theme.name || theme.id)) || ""),
        }))
        .filter((theme) => theme.id);
}

// Each theme is a folder, so it can carry its own fonts and images next to theme.css
function themeHref(name) {
    return `themes/${validTheme(name) || DEFAULT_THEME}/theme.css`;
}

function chooseTheme(config, search, storage) {
    const params = new URLSearchParams(search !== undefined ? search : window.location.search);
    const fromAddress = validTheme(params.get("theme"));
    const known = availableThemes(config).map((theme) => theme.id);

    let saved = readSavedTheme(storage);
    if (saved && known.length > 0 && !known.includes(saved)) {
        // The saved theme was removed from the server; forget it
        writeSavedTheme(null, storage);
        saved = null;
    }

    const server = validTheme(config && config.theme) || DEFAULT_THEME;
    const remembered = saved || sessionTheme;

    return { wanted: fromAddress || remembered || server, fromAddress, saved: remembered, server };
}

function loadStylesheet(link, href) {
    return new Promise((resolve) => {
        link.onload = () => resolve(true);
        link.onerror = () => resolve(false);
        link.href = href;
    });
}

// Lets phones color their browser bar to match the theme
function updateThemeColor() {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
        return;
    }
    const background = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    if (background) {
        meta.setAttribute("content", background);
    }
}

async function applyTheme(config) {
    try {
        const { wanted } = chooseTheme(config);
        const link = document.getElementById("theme");
        const href = themeHref(wanted);

        if (link.getAttribute("href") !== href) {
            const loaded = await loadStylesheet(link, href);
            if (!loaded) {
                console.error(`Theme "${wanted}" not found; using ${DEFAULT_THEME}`);
                await loadStylesheet(link, themeHref(DEFAULT_THEME));
            }
        }

        document.documentElement.dataset.theme = wanted;
        updateThemeColor();
    } finally {
        document.body.classList.remove("theme-loading");
    }
}

// ---- On-screen theme switcher ---------------------------------------------

let themeConfig = {};
let themeSwitcherWired = false;

function themePanelOpen() {
    return !document.getElementById("themePanel").hidden;
}

function openThemePanel() {
    buildThemeList();
    document.getElementById("themePanel").hidden = false;
    document.getElementById("themeButton").setAttribute("aria-expanded", "true");
    const selected = document.querySelector('.theme-option[aria-checked="true"]');
    if (selected) {
        selected.focus();
    }
}

function closeThemePanel() {
    document.getElementById("themePanel").hidden = true;
    document.getElementById("themeButton").setAttribute("aria-expanded", "false");
}

function removeThemeFromAddress() {
    const url = new URL(window.location.href);
    if (url.searchParams.has("theme")) {
        url.searchParams.delete("theme");
        window.history.replaceState(null, "", url.toString());
    }
}

function buildThemeList() {
    const list = document.getElementById("themeList");
    const note = document.getElementById("themeNote");
    const reset = document.getElementById("themeReset");
    const { wanted, saved, server } = chooseTheme(themeConfig);
    const themes = availableThemes(themeConfig);

    list.replaceChildren();
    for (const theme of themes) {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "theme-option";
        option.setAttribute("role", "menuitemradio");
        option.setAttribute("aria-checked", String(theme.id === wanted));
        option.textContent = theme.name || theme.id;
        option.addEventListener("click", () => selectTheme(theme.id));
        list.appendChild(option);
    }

    const serverName = (themes.find((theme) => theme.id === server) || {}).name || server;
    reset.hidden = !saved;
    reset.textContent = `Use server default (${serverName})`;
    note.textContent = saved ? "Saved in this browser." : "Using the server's theme.";
}

async function selectTheme(id) {
    const stored = writeSavedTheme(id);
    sessionTheme = stored ? null : id;
    removeThemeFromAddress();
    await applyTheme(themeConfig);
    buildThemeList();

    if (!stored) {
        document.getElementById("themeNote").textContent = "This browser blocks saving; the choice lasts until you reload.";
    }
}

async function resetTheme() {
    writeSavedTheme(null);
    sessionTheme = null;
    removeThemeFromAddress();
    await applyTheme(themeConfig);
    buildThemeList();
}

function wireThemeSwitcher() {
    const button = document.getElementById("themeButton");
    const panel = document.getElementById("themePanel");

    button.addEventListener("click", () => {
        if (themePanelOpen()) {
            closeThemePanel();
        } else {
            openThemePanel();
        }
    });

    document.getElementById("themeReset").addEventListener("click", resetTheme);

    document.addEventListener("click", (event) => {
        if (themePanelOpen() && !panel.contains(event.target) && !button.contains(event.target)) {
            closeThemePanel();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && themePanelOpen()) {
            closeThemePanel();
            button.focus();
        }
    });

    themeSwitcherWired = true;
}

// Shows the switcher button when the server allows it and there is more than one theme
function renderThemeSwitcher(config) {
    themeConfig = config || {};

    const button = document.getElementById("themeButton");
    const allowed = !(themeConfig.ui && themeConfig.ui.theme_switcher === false);
    const enabled = allowed && availableThemes(themeConfig).length > 1;

    button.hidden = !enabled;

    if (!enabled) {
        closeThemePanel();
        return;
    }

    if (!themeSwitcherWired) {
        wireThemeSwitcher();
    }

    if (themePanelOpen()) {
        buildThemeList();
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { DEFAULT_THEME, THEME_STORAGE_KEY, validTheme, readSavedTheme, writeSavedTheme, availableThemes, chooseTheme, themeHref };
}
