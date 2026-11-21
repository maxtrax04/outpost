// Outpost sensor panel (docs/sensors-design.md): readings from Home Assistant that the server lists
// at api/sensors (OUTPOST_SENSORS), shown as tiles like the weather readings. Shown only when
// /api/status says sensors are on, and read every REFRESH_MS while it is.
//
// Each tile is a .detail-box with data-metric="sensor", data-sensor-kind (number, binary, or text),
// data-device-class (Home Assistant's, such as temperature or door), data-state="on" or "off" for
// on/off sensors, and data-missing when there is no reading, so a theme can style any of them.

(function (root) {
    "use strict";

    const REFRESH_MS = 15 * 1000;
    const KINDS = ["number", "binary", "text"];

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

    function panel() {
        return root.document.getElementById("sensorsPanel");
    }

    function show(visible) {
        const element = panel();
        if (element && element.hidden === visible) {
            element.hidden = !visible;
            if (root.OutpostFit) root.OutpostFit.schedule();
        }
    }

    function render(answer) {
        const list = root.document.getElementById("sensors");
        if (!list) return;
        const tiles = readings(answer);
        const count = list.children.length;
        list.replaceChildren(...tiles.map((data) => tile(root.document, data)));
        show(tiles.length > 0);
        if (tiles.length !== count && root.OutpostFit) root.OutpostFit.schedule();
    }

    async function load() {
        const mine = ++request;
        try {
            const response = await root.fetch(`api/sensors?cacheBust=${Date.now()}`);
            if (mine !== request || !on) return;
            if (response.status === 404) {
                show(false); // turned off on the server
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
            show(false);
            return;
        }
        if (!timer) {
            load();
            timer = root.setInterval(load, REFRESH_MS);
        }
    }

    const api = { REFRESH_MS, valueText, tileData, readings, start };

    root.OutpostSensors = api;

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
