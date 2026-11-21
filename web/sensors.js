// Outpost sensor and power panels (docs/sensors-design.md): readings from Home Assistant that the
// server lists at api/sensors (OUTPOST_SENSORS and OUTPOST_POWER_*), shown as tiles like the weather
// readings. Read only when /api/status says sensors are on, every REFRESH_MS while it is. Each panel
// is shown when the answer has readings for it; #homePanels, which holds both, when either is.
//
// A sensor tile is a .detail-box.sensor with data-metric="sensor", data-sensor-kind (number, binary,
// or text), data-device-class (Home Assistant's, such as temperature or door), data-state="on" or
// "off" for on/off sensors, and data-missing when there is no reading.
//
// A power tile is a .detail-box.power with data-metric="power-<role>" and data-power-role (home,
// solar, grid, battery). The grid's has data-direction (import, export, idle) and a .power-direction
// note. The battery's has --value (its charge, 0 to 1) and data-gauge, like the weather gauges, so a
// theme's dial or bar shows it, and a .power-bar that themes without gauges show.

(function (root) {
    "use strict";

    const REFRESH_MS = 15 * 1000;
    const KINDS = ["number", "binary", "text"];
    const ROLES = ["home", "solar", "grid", "battery"];
    const DIRECTIONS = { import: "Importing", export: "Exporting", idle: "Idle" };

    let on = false;
    let timer = null;
    let request = 0;

    // "21.5°C", "45%", "1.2 kW", "Open", or "--"
    function valueText(sensor) {
        if (!sensor || sensor.missing || typeof sensor.text !== "string" || sensor.text === "") return "--";
        const unit = typeof sensor.unit === "string" ? sensor.unit : "";
        if (!unit) return sensor.text;
        return unit.startsWith("°") || unit === "%" ? `${sensor.text}${unit}` : `${sensor.text} ${unit}`;
    }

    // What a tile shows and is marked with, from one reading of api/sensors
    function tileData(sensor) {
        const reading = sensor && typeof sensor === "object" ? sensor : {};
        const kind = KINDS.includes(reading.kind) ? reading.kind : "text";
        const missing = reading.missing !== false || valueText(reading) === "--";
        const deviceClass = typeof reading.device_class === "string" && /^[a-z0-9_]{1,40}$/.test(reading.device_class)
            ? reading.device_class : "";
        return {
            label: typeof reading.label === "string" && reading.label ? reading.label : "Sensor",
            value: missing ? "--" : valueText(reading),
            kind,
            deviceClass,
            state: kind === "binary" && !missing ? (reading.value ? "on" : "off") : "",
            missing,
        };
    }

    // The readings in an api/sensors answer (anything else in it is ignored)
    function readings(answer) {
        return answer && Array.isArray(answer.sensors) ? answer.sensors.slice(0, 24).map(tileData) : [];
    }

    // What a power tile shows, from one power reading of api/sensors (null when it has no known role)
    function powerData(reading) {
        if (!reading || typeof reading !== "object" || !ROLES.includes(reading.role)) return null;
        const data = tileData(reading);
        const direction = reading.role === "grid" && !data.missing && Object.hasOwn(DIRECTIONS, reading.direction)
            ? reading.direction : "";
        const fraction = reading.role === "battery" && !data.missing && typeof reading.fraction === "number"
            && Number.isFinite(reading.fraction) ? Math.min(1, Math.max(0, reading.fraction)) : null;
        return {
            role: reading.role,
            label: data.label === "Sensor" ? reading.role[0].toUpperCase() + reading.role.slice(1) : data.label,
            value: data.value,
            missing: data.missing,
            direction,
            note: direction ? DIRECTIONS[direction] : "",
            fraction,
        };
    }

    // The power roles in an answer, each once, in the order home, solar, grid, battery
    function powerReadings(answer) {
        const list = answer && Array.isArray(answer.power) ? answer.power.map(powerData).filter(Boolean) : [];
        return ROLES.map((role) => list.find((data) => data.role === role)).filter(Boolean);
    }

    function tile(doc, data) {
        const box = doc.createElement("div");
        box.className = "detail-box sensor";
        box.dataset.metric = "sensor";
        box.dataset.sensorKind = data.kind;
        if (data.deviceClass) box.dataset.deviceClass = data.deviceClass;
        if (data.state) box.dataset.state = data.state;
        box.toggleAttribute("data-missing", data.missing);
        const value = doc.createElement("span");
        value.className = "sensor-value";
        value.textContent = data.value;
        // Labels come from Home Assistant, so they go in as text, never as markup
        box.append(doc.createTextNode(data.label), doc.createElement("br"), value);
        return box;
    }

    function powerTile(doc, data) {
        const box = doc.createElement("div");
        box.className = "detail-box power";
        box.dataset.metric = `power-${data.role}`;
        box.dataset.powerRole = data.role;
        if (data.direction) box.dataset.direction = data.direction;
        box.toggleAttribute("data-missing", data.missing);
        const value = doc.createElement("span");
        value.className = "sensor-value";
        value.textContent = data.value;
        box.append(doc.createTextNode(data.label), doc.createElement("br"), value);
        if (data.note) {
            const note = doc.createElement("small");
            note.className = "reading-note power-direction";
            note.textContent = data.note;
            box.append(note);
        }
        if (data.role === "battery") {
            box.toggleAttribute("data-gauge", true);
            if (data.fraction === null) {
                box.style.removeProperty("--value");
                box.toggleAttribute("data-missing", true);
            } else {
                box.style.setProperty("--value", data.fraction.toFixed(3));
            }
            const bar = doc.createElement("span");
            bar.className = "power-bar";
            box.append(bar);
        }
        return box;
    }

    function element(id) {
        return root.document.getElementById(id);
    }

    function setHidden(target, hidden) {
        if (target && target.hidden !== hidden) {
            target.hidden = hidden;
            return true;
        }
        return false;
    }

    // Shows each panel that has readings, and their wrapper when either does
    function show(sensorsVisible, powerVisible) {
        let changed = setHidden(element("sensorsPanel"), !sensorsVisible);
        changed = setHidden(element("powerPanel"), !powerVisible) || changed;
        changed = setHidden(element("homePanels"), !sensorsVisible && !powerVisible) || changed;
        if (changed && root.OutpostFit) root.OutpostFit.schedule();
    }

    function fill(list, tiles) {
        if (!list) return false;
        const count = list.children.length;
        list.replaceChildren(...tiles);
        return tiles.length !== count;
    }

    function render(answer) {
        const doc = root.document;
        const sensorTiles = readings(answer);
        const powerTiles = powerReadings(answer);
        let changed = fill(element("sensors"), sensorTiles.map((data) => tile(doc, data)));
        changed = fill(element("power"), powerTiles.map((data) => powerTile(doc, data))) || changed;
        show(sensorTiles.length > 0, powerTiles.length > 0);
        if (changed && root.OutpostFit) root.OutpostFit.schedule();
    }

    async function load() {
        const mine = ++request;
        try {
            const response = await root.fetch(`api/sensors?cacheBust=${Date.now()}`);
            if (mine !== request || !on) return;
            if (response.status === 404) {
                show(false, false); // turned off on the server
                return;
            }
            if (!response.ok) return; // keep the last readings; the API may be restarting
            render(await response.json());
        } catch (error) {
            // Keep the last readings
        }
    }

    // Called on every refresh with whether /api/status says sensors are on
    function start(sensorsOn) {
        on = Boolean(sensorsOn);
        if (!on) {
            if (timer) root.clearInterval(timer);
            timer = null;
            show(false, false);
            return;
        }
        if (!timer) {
            load();
            timer = root.setInterval(load, REFRESH_MS);
        }
    }

    const api = { REFRESH_MS, valueText, tileData, readings, powerData, powerReadings, start };

    root.OutpostSensors = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
