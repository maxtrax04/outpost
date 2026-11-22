# Outpost add-on

Outpost is a self-hosted weather dashboard for wall displays and phones. This add-on runs it inside
Home Assistant and adds an **Outpost** panel to the sidebar.

The add-on is experimental: it has not yet been tried on every kind of Home Assistant installation.
Please report problems at https://github.com/maxtrax04/outpost/issues.

## Installation

1. In Home Assistant, go to **Settings > Apps > Install app** (add-ons are called apps since Home
   Assistant 2026.2), open the menu (⋮) in the top-right corner, and choose **Repositories**.
2. Add `https://github.com/maxtrax04/outpost-addon` and close the dialog.
3. Find **Outpost** in the store, install it, and start it.
4. Open it with **Open web UI**, or turn on **Show in sidebar** on its page for an **Outpost** item in
   the sidebar. The item shows for every Home Assistant user, not only administrators.

To try beta versions before they are released, add `https://github.com/maxtrax04/outpost-addon#beta`
instead. Beta versions may have problems that the released version doesn't.

## Location, time zone, and units

Unless you set them in the add-on's options, Outpost uses Home Assistant's own home location, home name,
time zone, and unit system (metric or US customary), read when the add-on starts. To show somewhere
else, set both **Latitude** and **Longitude**.

## Options

Each option is one of Outpost's settings, described in full in the README:
https://github.com/maxtrax04/outpost#settings. The option `map_zoom` is the setting `OUTPOST_MAP_ZOOM`,
and so on; **Time zone** is `TZ`. Empty options use Outpost's defaults. Press **Save** at the bottom
of the options; Home Assistant forgets changes that aren't saved. Changes take effect when the add-on
restarts. Each start, the **Log** tab lists the options Outpost received (switches as on or off; keys,
addresses, and other text only as "set").

Some options worth knowing:

- **Weather source**: `auto` picks the best one for your location. **Contact** (an email address or
  website) is needed for MET Norway and the National Weather Service, which `auto` uses in the Nordic
  countries and the US.
- **Map**: a map of the place shown, with rain radar. With OpenStreetMap's tiles (the default) it needs
  **Contact** too.
- **Location search**: lets viewers look at the weather somewhere else from the panel on screen. Turn it
  off if only home should be shown.
- **Sensors**: Home Assistant entities to show on the dashboard, one per line, such as
  `sensor.living_room_temperature`. Put a label before `=` and a unit in brackets after it if you like:
  `Garage=binary_sensor.garage_door`. The add-on reads them from Home Assistant itself, with no token to
  set. It only reads the entities listed. Anyone who can open the dashboard sees them.
- **Power**: for the power panel, one entity each for home use, solar, grid, and battery charge (leave out
  the ones you don't have). Grid is positive when importing; turn on **Flip the grid sign** if your meter
  counts exports as positive.

## Wall tablets and other screens

The sidebar panel works for anyone logged in to Home Assistant. A wall tablet or a phone that isn't
logged in can open Outpost on its own port instead:

1. On the add-on's **Configuration** tab, under **Network**, enter a port, such as `8088`.
2. Restart the add-on and open `http://homeassistant.local:8088` (your Home Assistant's address, with
   that port) on the screen.

Anyone on your network can then open it, as with Outpost on its own.

## Your own themes

Put a theme folder (with its `theme.css`) in the add-on's configuration folder, under `themes/`. With the
Samba or File editor add-ons, that folder is `addon_configs/<id>_outpost/themes/`. Then choose it as
**Theme**, or in the panel on screen. See https://github.com/maxtrax04/outpost/blob/main/docs/themes.md.

## Sensors and the weather entity

Outpost's readings can also become Home Assistant sensors and a weather entity; see
https://github.com/maxtrax04/outpost/blob/main/docs/home-assistant.md. With the add-on, give it a port as
above, and use `http://homeassistant.local:<port>` as Outpost's address there.

## Privacy

Outpost sends your location only to the weather services you choose (and, with the map, the map and
radar tiles it shows), and does not log it. The add-on reads Home Assistant's configuration only for
the location, time zone, and units, once at startup, and the entities listed under **Sensors** and
**Power**, every **Sensor interval** seconds (10 by default).
