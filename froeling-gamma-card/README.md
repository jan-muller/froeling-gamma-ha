# froeling-gamma-card

Lovelace card for Home Assistant that shows the heating installation as a schematic:
Fröling wood boiler → buffer tank → mixing valve → radiators, plus the domestic hot-water cylinder.
Live values from the EBV Gamma 23 B (via [gamma2mqtt](../gamma2mqtt)) sit as chips where they
belong; pipes animate when there is flow and the boiler shows fire when it is hot.
The **ignition request** (the flame symbol on the Gamma display) lights up orange.

![preview](../docs/card-preview.png)

## Installation

**HACS (recommended):** HACS → Frontend → ⋮ → *Custom repositories* → URL of this repository,
category *Dashboard*. Then install the card; HACS registers the resource for you.

**Manual:** copy `dist/froeling-gamma-card.js` (repository root) to `config/www/` and add
`/local/froeling-gamma-card.js` (JavaScript module) under *Settings → Dashboards → ⋮ → Resources*.

## Configuration

See [`example-dashboard.yaml`](example-dashboard.yaml). All entities default to the ids that
gamma2mqtt creates (`sensor.gamma_*`), so `type: custom:froeling-gamma-card` without any further
options already works.

| Option | Default | Meaning |
|---|---|---|
| `title` | `Verwarming` | Card header (`show_header: false` hides it) |
| `show_tiles` | `true` | Tile row below the schematic |
| `entities.*` | `sensor.gamma_*` | See the example; `buffer_top`, `buffer_bottom`, `hot_water`, `boiler_pump`, `hot_water_pump` are optional (UVS 42) |
| `thresholds.flow_active` | `28` | Flow temperature above which the heating circuit animates |
| `thresholds.boiler_active` | `60` | Boiler temperature above which fire and the charging pump animate (only without `boiler_pump`) |

Clicking a chip or tile opens the *more-info* dialog of that entity.
If `binary_sensor.gamma_flame_request` carries the attribute `confidence: candidate`, the card shows
"experimenteel · 2004 P19" below the ignition request.

Labels on the card are in Dutch, matching the entity names gamma2mqtt creates.

## Development

No build step. Open `dev/preview.html` in a browser; it loads `../../dist/froeling-gamma-card.js` with a
mock `hass` object and buttons for four scenarios (flame on, boiler hot, with UVS 42, offline).
Chip coordinates live in `CHIPS` (viewBox 1000×560) and must stay in sync with the SVG in `sceneSvg()`.
