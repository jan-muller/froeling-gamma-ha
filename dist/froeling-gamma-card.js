/*
 * froeling-gamma-card — Home Assistant Lovelace card for a Fröling wood boiler
 * installation controlled by an EBV Gamma 23 B (entities from gamma2mqtt) and,
 * optionally, a Technische Alternative UVS 42 (buffer / hot-water sensors).
 *
 * No build step, no dependencies. Register as a Lovelace resource:
 *   /hacsfiles/froeling-gamma-card/froeling-gamma-card.js   (HACS)
 *   /local/froeling-gamma-card.js                           (manual copy to www/)
 */

const CARD_VERSION = "0.1.0";

/* ------------------------------------------------------------------ config */

const DEFAULT_ENTITIES = {
  outside: "sensor.gamma_outside_temperature",
  boiler: "sensor.gamma_boiler_temperature",
  flow: "sensor.gamma_heating_flow_temperature",
  room: "sensor.gamma_room_temperature",
  room_target: "sensor.gamma_room_target_temperature",
  hot_water_target: "sensor.gamma_hot_water_target",
  mode: "sensor.gamma_operating_mode",
  flame: "binary_sensor.gamma_flame_request",
  // Optional, typically from a UVS 42 bridge later on:
  buffer_top: null,
  buffer_bottom: null,
  hot_water: null,
  boiler_pump: null,
  hot_water_pump: null,
};

const DEFAULT_THRESHOLDS = {
  flow_active: 28, // °C: heating circuit considered active above this flow temp
  boiler_active: 60, // °C: boiler considered to be firing above this temperature
};

const MODE_LABELS = {
  auto: "Automatisch",
  heating: "Verwarmen",
  reduced: "Verlaagd",
  party: "Party",
  absent: "Afwezig",
  holiday: "Vakantie",
  unknown: "Onbekend",
};

const MODE_ICONS = {
  auto: "mdi:calendar-clock",
  heating: "mdi:radiator",
  reduced: "mdi:weather-night",
  party: "mdi:party-popper",
  absent: "mdi:home-export-outline",
  holiday: "mdi:beach",
  unknown: "mdi:help-circle-outline",
};

/* Chip definitions: where each value sits on the schematic (viewBox 1000x560). */
const CHIPS = [
  { id: "outside", x: 40, y: 56, anchor: "left", label: "Buiten", tone: "sky", bar: [-15, 35] },
  { id: "mode", x: 940, y: 60, anchor: "right", label: "Gamma 23 B", tone: "steel" },
  { id: "boiler", x: 178, y: 262, label: "Houtketel", tone: "ember", bar: [20, 95] },
  { id: "flame", x: 330, y: 112, label: "Vlamsymbool", tone: "flame" },
  { id: "buffer_top", x: 388, y: 246, label: "Buffer boven", tone: "ember", bar: [20, 95] },
  { id: "buffer_bottom", x: 388, y: 392, label: "Buffer onder", tone: "ember", bar: [20, 95] },
  { id: "hot_water", x: 578, y: 300, label: "Warm water", tone: "water", bar: [20, 75] },
  { id: "hot_water_target", x: 578, y: 418, label: "Warmwater doel", tone: "water", small: true },
  { id: "flow", x: 668, y: 160, label: "Aanvoer", tone: "ember", bar: [15, 70] },
  { id: "room", x: 822, y: 282, label: "Kamer", tone: "leaf", bar: [12, 28] },
];

/* --------------------------------------------------------------- helpers */

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function numeric(state) {
  if (!state || state.state === "unavailable" || state.state === "unknown" || state.state === "") return null;
  const n = Number(state.state);
  return Number.isFinite(n) ? n : null;
}

function fmtTemp(value, decimals = 1) {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: decimals });
}

function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

function fmtAge(ms) {
  if (!Number.isFinite(ms)) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.round(m / 60);
  return `${h} u`;
}

/* ------------------------------------------------------------------ styles */

const STYLE = `
:host {
  --fg-bg: #0a1220;
  --fg-bg-2: #101c2f;
  --fg-line: rgba(144, 176, 214, 0.14);
  --fg-text: #e6eef9;
  --fg-muted: #8fa3bd;
  --fg-ember: #ff9a3c;
  --fg-ember-2: #ff5e3a;
  --fg-steel: #8fb5ff;
  --fg-water: #4fd1ff;
  --fg-sky: #9ad8ff;
  --fg-leaf: #7be3a4;
  --fg-flame: #ffb347;
  --fg-cold: #4a7bd6;
  --fg-chip: rgba(10, 18, 32, 0.78);
  --fg-radius: 18px;
  display: block;
}
ha-card {
  background:
    radial-gradient(900px 420px at 18% 70%, rgba(255, 120, 50, 0.10), transparent 60%),
    radial-gradient(700px 400px at 85% 25%, rgba(79, 160, 255, 0.10), transparent 60%),
    linear-gradient(180deg, var(--fg-bg) 0%, var(--fg-bg-2) 100%);
  color: var(--fg-text);
  overflow: hidden;
  border-radius: var(--ha-card-border-radius, 12px);
  font-family: var(--paper-font-body1_-_font-family, "Roboto", sans-serif);
}
.head {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 20px 6px 20px;
}
.head h1 {
  margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: 0.01em; flex: 1;
}
.status {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 0.72rem; color: var(--fg-muted); letter-spacing: 0.06em; text-transform: uppercase;
}
.status .dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--fg-leaf);
  box-shadow: 0 0 0 3px rgba(123, 227, 164, 0.18);
}
.status.offline .dot { background: #ff5e3a; box-shadow: 0 0 0 3px rgba(255, 94, 58, 0.18); }
.status.stale .dot { background: var(--fg-ember); box-shadow: 0 0 0 3px rgba(255, 154, 60, 0.18); }

.scene {
  position: relative; margin: 6px 12px 0 12px;
  container-type: inline-size;
  aspect-ratio: 1000 / 560;
  border-radius: var(--fg-radius);
  overflow: hidden;
  border: 1px solid var(--fg-line);
  background:
    linear-gradient(var(--fg-line) 1px, transparent 1px) 0 0 / 40px 40px,
    linear-gradient(90deg, var(--fg-line) 1px, transparent 1px) 0 0 / 40px 40px,
    linear-gradient(180deg, rgba(14, 24, 42, 0.55), rgba(8, 14, 26, 0.85));
}
.scene svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }

/* --- SVG --- */
.outline { fill: rgba(16, 28, 47, 0.9); stroke: rgba(170, 196, 230, 0.55); stroke-width: 2; }
.outline.soft { fill: rgba(16, 28, 47, 0.65); stroke: rgba(170, 196, 230, 0.35); }
.detail { fill: none; stroke: rgba(170, 196, 230, 0.35); stroke-width: 1.5; }
.detail.fill { fill: rgba(170, 196, 230, 0.08); }
.caption { fill: var(--fg-muted); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }
.floor { stroke: rgba(170, 196, 230, 0.25); stroke-width: 2; stroke-dasharray: 2 8; }

.pipe { fill: none; stroke-width: 7; stroke-linecap: round; stroke-linejoin: round; }
.pipe.hot { stroke: rgba(255, 140, 60, 0.28); }
.pipe.cold { stroke: rgba(74, 123, 214, 0.28); }
.pipe.water { stroke: rgba(79, 209, 255, 0.22); }
.flow { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 10 16; opacity: 0; transition: opacity 0.6s; }
.flow.hot { stroke: var(--fg-ember); }
.flow.cold { stroke: var(--fg-steel); }
.flow.water { stroke: var(--fg-water); }
.flow.on { opacity: 1; animation: fg-flow 1.4s linear infinite; }
.flow.on.rev { animation-direction: reverse; }
@keyframes fg-flow { to { stroke-dashoffset: -26; } }

.pump { fill: rgba(16, 28, 47, 1); stroke: rgba(170, 196, 230, 0.55); stroke-width: 2; }
.pump-blade { fill: rgba(170, 196, 230, 0.6); transform-box: fill-box; transform-origin: center; }
.pump.on + .pump-blade { fill: var(--fg-ember); animation: fg-spin 1.2s linear infinite; }
@keyframes fg-spin { to { transform: rotate(360deg); } }

.fire { transform-box: fill-box; transform-origin: 50% 100%; opacity: 0.25; transition: opacity 0.6s; }
.fire.on { opacity: 1; }
.fire.on .f1 { animation: fg-flicker 0.9s ease-in-out infinite alternate; }
.fire.on .f2 { animation: fg-flicker 0.7s ease-in-out infinite alternate-reverse; }
.fire.on .f3 { animation: fg-flicker 1.1s ease-in-out infinite alternate; }
.fire path { transform-box: fill-box; transform-origin: 50% 100%; }
@keyframes fg-flicker {
  from { transform: scaleY(0.92) scaleX(1.04); }
  to { transform: scaleY(1.08) scaleX(0.96); }
}
.glow { opacity: 0; transition: opacity 0.8s; }
.glow.on { opacity: 1; animation: fg-breathe 2.4s ease-in-out infinite; }
@keyframes fg-breathe { 50% { opacity: 0.55; } }
.smoke { fill: none; stroke: rgba(200, 214, 235, 0.35); stroke-width: 2; stroke-linecap: round;
  opacity: 0; }
.smoke.on { opacity: 1; animation: fg-smoke 3s ease-in-out infinite; }
@keyframes fg-smoke { 0% { transform: translateY(0); opacity: 0; } 30% { opacity: .6; } 100% { transform: translateY(-26px); opacity: 0; } }

/* --- chips --- */
.overlay { position: absolute; inset: 0; pointer-events: none; }
.chip {
  position: absolute; transform: translate(-50%, -50%);
  pointer-events: auto; cursor: pointer;
  min-width: 9.6cqw; padding: 0.7cqw 1.1cqw 0.8cqw 1.1cqw;
  border-radius: 1.2cqw; background: var(--fg-chip);
  border: 1px solid rgba(170, 196, 230, 0.22);
  backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  transition: transform 0.2s ease, border-color 0.2s ease;
}
.chip:hover { transform: translate(-50%, -50%) scale(1.04); border-color: rgba(170, 196, 230, 0.5); }
.chip.left { transform: translate(0, -50%); }
.chip.left:hover { transform: translate(0, -50%) scale(1.04); }
.chip.right { transform: translate(-100%, -50%); }
.chip.right:hover { transform: translate(-100%, -50%) scale(1.04); }
.chip.hidden { display: none; }
.chip .label { font-size: clamp(0.5rem, 1.15cqw, 0.66rem); letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-muted); white-space: nowrap; }
.chip .value { font-size: clamp(0.75rem, 2.1cqw, 1.15rem); font-weight: 700; line-height: 1.15; font-variant-numeric: tabular-nums; white-space: nowrap; }
.chip.small .value { font-size: clamp(0.7rem, 1.7cqw, 0.95rem); }
.chip .value small { font-size: 0.7em; font-weight: 500; opacity: 0.8; margin-left: 1px; }
.chip .sub { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 0.5cqw; }
.chip .pill { font-size: clamp(0.5rem, 1.05cqw, 0.62rem); padding: 2px 7px; border-radius: 999px; background: rgba(170, 196, 230, 0.12); color: var(--fg-text); white-space: nowrap; }
.chip .bar { height: 4px; margin-top: 0.7cqw; border-radius: 4px; background: rgba(170, 196, 230, 0.14); overflow: hidden; }
.chip .bar i { display: block; height: 100%; width: 0; border-radius: 4px; transition: width 0.8s ease; }
.chip.unavailable { opacity: 0.55; }
.chip.unavailable .value { color: var(--fg-muted); }

.tone-ember .value { color: var(--fg-ember); } .tone-ember .bar i { background: var(--fg-ember); }
.tone-flame .value { color: var(--fg-flame); }
.tone-water .value { color: var(--fg-water); } .tone-water .bar i { background: var(--fg-water); }
.tone-sky .value { color: var(--fg-sky); } .tone-sky .bar i { background: var(--fg-sky); }
.tone-leaf .value { color: var(--fg-leaf); } .tone-leaf .bar i { background: var(--fg-leaf); }
.tone-steel .value { color: var(--fg-steel); }

.chip.chip-flame { border-color: rgba(255, 179, 71, 0.35); }
.chip.chip-flame.on { border-color: rgba(255, 179, 71, 0.8); box-shadow: 0 0 0 4px rgba(255, 154, 60, 0.12), 0 10px 30px rgba(255, 120, 50, 0.35);
  animation: fg-pulse 2s ease-in-out infinite; }
@keyframes fg-pulse { 50% { box-shadow: 0 0 0 8px rgba(255, 154, 60, 0.05), 0 10px 30px rgba(255, 120, 50, 0.45); } }
.chip.chip-flame .value { display: flex; align-items: center; gap: 6px; }
.chip.chip-flame ha-icon { --mdc-icon-size: 18px; color: var(--fg-flame); }
.chip .exp { font-size: clamp(0.48rem, 1cqw, 0.58rem); color: var(--fg-muted); letter-spacing: 0.04em; margin-top: 3px; }
.chip.chip-mode .value { display: flex; align-items: center; gap: 6px; font-size: clamp(0.72rem, 1.8cqw, 1rem); }
.chip.chip-mode ha-icon { --mdc-icon-size: 18px; }

/* --- tiles --- */
.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; padding: 12px 12px 14px 12px; }
.tile { border-radius: 14px; padding: 10px 12px 12px 12px; background: rgba(16, 28, 47, 0.65);
  border: 1px solid rgba(170, 196, 230, 0.14); border-left-width: 3px; cursor: pointer; transition: background 0.2s; }
.tile:hover { background: rgba(22, 38, 62, 0.85); }
.tile .label { font-size: 0.7rem; color: var(--fg-muted); letter-spacing: 0.06em; text-transform: uppercase; }
.tile .value { font-size: 1.35rem; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; margin-top: 2px; }
.tile .value small { font-size: 0.65em; font-weight: 500; opacity: 0.8; }
.tile .sub { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 6px; }
.tile .pill { font-size: 0.64rem; padding: 2px 8px; border-radius: 999px; background: rgba(170, 196, 230, 0.12); }
.tile .bar { height: 5px; margin-top: 9px; border-radius: 4px; background: rgba(170, 196, 230, 0.14); overflow: hidden; }
.tile .bar i { display: block; height: 100%; width: 0; border-radius: 4px; transition: width 0.8s ease; }
.tile.tone-ember { border-left-color: var(--fg-ember); }
.tile.tone-water { border-left-color: var(--fg-water); }
.tile.tone-sky { border-left-color: var(--fg-sky); }
.tile.tone-leaf { border-left-color: var(--fg-leaf); }
.tile.tone-steel { border-left-color: var(--fg-steel); }
.tile.tone-flame { border-left-color: var(--fg-flame); }
.tile.unavailable { opacity: 0.55; }
.tile.hidden { display: none; }
.tile.on { border-color: rgba(255, 179, 71, 0.6); border-left-color: var(--fg-flame); background: rgba(255, 154, 60, 0.08); }

.banner { margin: 10px 12px 0 12px; padding: 10px 14px; border-radius: 12px; font-size: 0.82rem;
  background: rgba(255, 94, 58, 0.12); border: 1px solid rgba(255, 94, 58, 0.35); color: #ffb4a3; display: none; }
.banner.show { display: block; }

@container (max-width: 640px) {
  .chip .sub, .chip .exp { display: none; }
  .chip { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35); }
}
@container (max-width: 440px) {
  .chip .bar { display: none; }
  .chip .label { letter-spacing: 0.04em; }
}
@media (prefers-reduced-motion: reduce) {
  .flow.on, .pump.on + .pump-blade, .fire.on path, .glow.on, .smoke.on, .chip.chip-flame.on { animation: none; }
}
`;

/* -------------------------------------------------------------- SVG scene */

function sceneSvg() {
  // Coordinates in a 1000 x 560 viewBox. Keep CHIPS in sync when moving things.
  return `
<svg viewBox="0 0 1000 560" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="fg-tank" x1="0" x2="1">
      <stop offset="0" stop-color="rgba(170,196,230,0.02)"/>
      <stop offset="0.5" stop-color="rgba(170,196,230,0.12)"/>
      <stop offset="1" stop-color="rgba(170,196,230,0.02)"/>
    </linearGradient>
    <radialGradient id="fg-glow" r="0.5">
      <stop offset="0" stop-color="#ff7a2a" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#ff7a2a" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="fg-fire" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0" stop-color="#ff4d1f"/>
      <stop offset="0.6" stop-color="#ff9a3c"/>
      <stop offset="1" stop-color="#ffe08a"/>
    </linearGradient>
    <linearGradient id="fg-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="rgba(120,180,255,0.10)"/>
      <stop offset="1" stop-color="rgba(120,180,255,0)"/>
    </linearGradient>
  </defs>

  <!-- floor -->
  <line class="floor" x1="40" y1="492" x2="960" y2="492"/>

  <!-- ===== Wood boiler (Fröling) ===== -->
  <ellipse id="boiler-glow" class="glow" cx="178" cy="420" rx="150" ry="110" fill="url(#fg-glow)"/>
  <rect x="150" y="150" width="28" height="60" class="outline soft"/>
  <path id="smoke1" class="smoke" d="M164 146 c -6 -10 6 -16 0 -26 c -5 -9 5 -14 0 -22"/>
  <rect x="108" y="200" width="140" height="290" rx="10" class="outline"/>
  <rect x="124" y="214" width="108" height="50" rx="6" class="detail fill"/>
  <rect x="124" y="330" width="108" height="112" rx="8" class="detail fill"/>
  <rect x="140" y="346" width="76" height="60" rx="5" class="detail"/>
  <!-- fire behind the door glass -->
  <g id="fire" class="fire">
    <path class="f1" d="M178 404 c -22 -10 -26 -36 -6 -54 c 2 12 10 16 12 10 c 4 -10 -4 -22 4 -34 c 18 16 26 44 2 62 c -2 2 -8 6 -12 16 z" fill="url(#fg-fire)"/>
    <path class="f2" d="M160 404 c -12 -8 -10 -24 2 -32 c 0 8 6 10 8 6 c 2 -6 -2 -12 2 -18 c 10 10 12 28 0 38 z" fill="url(#fg-fire)" opacity="0.85"/>
    <path class="f3" d="M196 404 c -8 -6 -8 -18 0 -26 c 0 6 4 8 6 4 c 2 -4 -2 -8 2 -12 c 8 8 8 22 0 30 z" fill="url(#fg-fire)" opacity="0.85"/>
  </g>
  <circle cx="226" cy="300" r="5" class="detail"/>
  <line x1="124" y1="456" x2="232" y2="456" class="detail"/>
  <text x="178" y="520" text-anchor="middle" class="caption">Fröling</text>

  <!-- ===== Buffer tank ===== -->
  <rect x="330" y="170" width="116" height="320" rx="46" class="outline"/>
  <rect x="330" y="170" width="116" height="320" rx="46" fill="url(#fg-tank)"/>
  <line x1="344" y1="280" x2="432" y2="280" class="detail" stroke-dasharray="3 6"/>
  <line x1="344" y1="330" x2="432" y2="330" class="detail" stroke-dasharray="3 6"/>
  <line x1="344" y1="380" x2="432" y2="380" class="detail" stroke-dasharray="3 6"/>
  <text x="388" y="520" text-anchor="middle" class="caption">Buffer</text>

  <!-- ===== Hot water boiler ===== -->
  <rect x="528" y="230" width="100" height="260" rx="40" class="outline"/>
  <rect x="528" y="230" width="100" height="260" rx="40" fill="url(#fg-tank)"/>
  <path class="detail" d="M548 372 h60 M548 388 h60 M548 404 h60 M548 420 h60 M548 436 h60 M548 372 c -10 0 -10 16 0 16 M548 404 c -10 0 -10 16 0 16 M608 388 c 10 0 10 16 0 16 M608 420 c 10 0 10 16 0 16"/>
  <!-- tap -->
  <path class="detail" d="M578 230 v-40 h28 v12 M598 190 v-14"/>
  <path id="tap-drop" class="detail" d="M606 212 c -4 6 -4 10 0 10 c 4 0 4 -4 0 -10 z" fill="rgba(79,209,255,0.6)" stroke="none"/>
  <text x="578" y="520" text-anchor="middle" class="caption">Boiler</text>

  <!-- ===== House with radiator ===== -->
  <rect x="700" y="60" width="260" height="190" fill="url(#fg-sky)" rx="14"/>
  <path d="M700 232 L822 118 L944 232" class="outline soft" fill="none"/>
  <rect x="722" y="232" width="200" height="258" class="outline soft"/>
  <rect x="770" y="252" width="34" height="42" rx="3" class="detail fill"/>
  <rect x="840" y="252" width="34" height="42" rx="3" class="detail fill"/>
  <!-- radiator -->
  <rect x="756" y="386" width="132" height="70" rx="6" class="detail fill"/>
  <path class="detail" d="M772 386 v70 M790 386 v70 M808 386 v70 M826 386 v70 M844 386 v70 M862 386 v70"/>
  <text x="822" y="520" text-anchor="middle" class="caption">Woning</text>

  <!-- ===== Mixing valve ===== -->
  <path d="M652 196 l16 10 l-16 10 z M684 196 l-16 10 l16 10 z" class="outline"/>
  <path d="M668 206 v-16" class="detail"/>
  <path d="M662 190 h12" class="detail"/>

  <!-- ===== Pipes (static casing) ===== -->
  <!-- boiler -> buffer (supply, A1) -->
  <path id="p-boiler-supply" class="pipe hot" d="M248 236 H290 V200 H330"/>
  <path id="p-boiler-return" class="pipe cold" d="M330 450 H290 V420 H248"/>
  <!-- buffer -> mixer -> radiator (supply) -->
  <path id="p-heat-supply" class="pipe hot" d="M446 206 H756 V386"/>
  <!-- radiator -> buffer (return) -->
  <path id="p-heat-return" class="pipe cold" d="M888 456 V470 H668 V216 M668 470 H446 V456"/>
  <!-- buffer -> hot water boiler coil (A2) -->
  <path id="p-dhw-supply" class="pipe water" d="M446 280 H528"/>
  <path id="p-dhw-return" class="pipe water" d="M528 440 H490 V280"/>

  <!-- ===== Flow animations ===== -->
  <path id="f-boiler-supply" class="flow hot" d="M248 236 H290 V200 H330"/>
  <path id="f-boiler-return" class="flow cold" d="M330 450 H290 V420 H248"/>
  <path id="f-heat-supply" class="flow hot" d="M446 206 H756 V386"/>
  <path id="f-heat-return" class="flow cold" d="M888 456 V470 H446 V456"/>
  <path id="f-mix" class="flow cold" d="M668 470 V216"/>
  <path id="f-dhw-supply" class="flow water" d="M446 280 H528"/>
  <path id="f-dhw-return" class="flow water" d="M528 440 H490 V280"/>

  <!-- ===== Pumps ===== -->
  <circle id="pump-a1" class="pump" cx="290" cy="236" r="13"/>
  <path class="pump-blade" d="M284 228 L298 236 L284 244 z"/>
  <circle id="pump-a2" class="pump" cx="490" cy="360" r="12"/>
  <path class="pump-blade" d="M485 352 L497 360 L485 368 z"/>
  <circle id="pump-heat" class="pump" cx="600" cy="206" r="12"/>
  <path class="pump-blade" d="M595 198 L607 206 L595 214 z"/>

  <!-- ===== Outside: tree + sensor ===== -->
  <path d="M62 470 l-16 0 l12 -24 l-8 0 l12 -24 l-8 0 l14 -26 l14 26 l-8 0 l12 24 l-8 0 l12 24 z" class="outline soft"/>
  <rect x="59" y="470" width="6" height="20" class="outline soft"/>
</svg>`;
}

/* ----------------------------------------------------------------- card */

class FroelingGammaCard extends HTMLElement {
  static getStubConfig() {
    return { title: "Verwarming", entities: { ...DEFAULT_ENTITIES }, show_tiles: true };
  }

  setConfig(config) {
    if (!config) throw new Error("Configuratie ontbreekt");
    this._config = {
      title: "Verwarming",
      show_tiles: true,
      show_header: true,
      ...config,
      entities: { ...DEFAULT_ENTITIES, ...(config.entities || {}) },
      thresholds: { ...DEFAULT_THRESHOLDS, ...(config.thresholds || {}) },
    };
    this._lastStates = null;
    this._render();
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._root) this._update();
  }

  getCardSize() {
    return this._config && this._config.show_tiles ? 9 : 6;
  }

  /* ---- DOM creation (once per config) ---- */
  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    const chips = CHIPS.map((c) => {
      const cls = ["chip", `tone-${c.tone}`, `chip-${c.id}`, c.anchor || "", c.small ? "small" : ""].join(" ");
      return `<div class="${cls}" data-id="${c.id}" style="left:${c.x / 10}%;top:${(c.y / 560) * 100}%">
        <div class="label">${esc(c.label)}</div>
        <div class="value">—</div>
        <div class="sub"></div>
        ${c.bar ? '<div class="bar"><i></i></div>' : ""}
        <div class="exp"></div>
      </div>`;
    }).join("");

    const tiles = CHIPS.map((c) => `<div class="tile tone-${c.tone} hidden" data-id="${c.id}">
          <div class="label">${esc(c.label)}</div>
          <div class="value">—</div>
          <div class="sub"></div>
          ${c.bar ? '<div class="bar"><i></i></div>' : ""}
        </div>`)
      .join("");

    root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        ${this._config.show_header ? `
        <div class="head">
          <h1>${esc(this._config.title)}</h1>
          <div class="status" id="status"><span class="dot"></span><span id="status-text">live</span></div>
        </div>` : ""}
        <div class="banner" id="banner"></div>
        <div class="scene">
          ${sceneSvg()}
          <div class="overlay">${chips}</div>
        </div>
        ${this._config.show_tiles ? `<div class="tiles">${tiles}</div>` : ""}
      </ha-card>`;
    this._root = root;

    root.querySelectorAll("[data-id]").forEach((el) => {
      el.addEventListener("click", () => this._moreInfo(el.dataset.id));
    });
  }

  _moreInfo(id) {
    const ent = this._entityFor(id);
    if (!ent || !this._hass || !this._hass.states[ent]) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: ent } }));
  }

  _entityFor(id) {
    const e = this._config.entities;
    return e[id] || null;
  }

  _state(id) {
    const ent = this._entityFor(id);
    return ent && this._hass ? this._hass.states[ent] || null : null;
  }

  /* ---- update (every hass change) ---- */
  _update() {
    const e = this._config.entities;
    const keys = Object.keys(e).filter((k) => e[k]);
    const sig = keys.map((k) => {
      const s = this._hass.states[e[k]];
      return s ? `${s.state}|${s.last_updated}` : "x";
    }).join(";");
    if (sig === this._lastStates) return;
    this._lastStates = sig;

    const th = this._config.thresholds;
    const r = this._root;

    const val = {};
    for (const k of keys) val[k] = numeric(this._hass.states[e[k]]);
    const flameState = this._state("flame");
    const flameOn = flameState ? flameState.state === "on" : null;

    // ---- derived activity ----
    const boilerPump = this._state("boiler_pump");
    const boilerLoading = boilerPump ? boilerPump.state === "on" : val.boiler !== null && val.boiler >= th.boiler_active;
    const dhwPump = this._state("hot_water_pump");
    const dhwLoading = dhwPump ? dhwPump.state === "on" : false;
    const modeState = this._state("mode");
    const mode = modeState ? modeState.state : null;
    const heating = val.flow !== null && val.flow >= th.flow_active && mode !== "holiday" && mode !== "absent";
    const boilerHot = val.boiler !== null && val.boiler >= th.boiler_active;

    this._toggle("#f-boiler-supply", boilerLoading);
    this._toggle("#f-boiler-return", boilerLoading);
    this._toggle("#pump-a1", boilerLoading);
    this._toggle("#f-heat-supply", heating);
    this._toggle("#f-heat-return", heating);
    this._toggle("#f-mix", heating);
    this._toggle("#pump-heat", heating);
    this._toggle("#f-dhw-supply", dhwLoading);
    this._toggle("#f-dhw-return", dhwLoading);
    this._toggle("#pump-a2", dhwLoading);
    this._toggle("#fire", boilerHot);
    this._toggle("#boiler-glow", boilerHot);
    this._toggle("#smoke1", boilerHot);

    // ---- chips & tiles ----
    const setBoth = (id, fn) => {
      r.querySelectorAll(`[data-id="${id}"]`).forEach((el) => fn(el));
    };
    const showTemp = (id, v, extraPills = [], expText = "") => {
      const state = this._state(id);
      const configured = !!this._entityFor(id);
      setBoth(id, (el) => {
        el.classList.toggle("hidden", !configured);
        el.classList.toggle("unavailable", configured && v === null);
        const value = el.querySelector(".value");
        value.innerHTML = v === null ? "—" : `${esc(fmtTemp(v))}<small>°C</small>`;
        const sub = el.querySelector(".sub");
        sub.innerHTML = extraPills.map((p) => `<span class="pill">${esc(p)}</span>`).join("");
        const chip = CHIPS.find((c) => c.id === id);
        const bar = el.querySelector(".bar i");
        if (bar && chip.bar) {
          const pct = v === null ? 0 : clamp01((v - chip.bar[0]) / (chip.bar[1] - chip.bar[0])) * 100;
          bar.style.width = `${pct}%`;
        }
        const exp = el.querySelector(".exp");
        if (exp) {
          const conf = state && state.attributes ? state.attributes.confidence : null;
          exp.textContent = expText || (conf === "probable" ? "waarschijnlijk" : conf === "candidate" ? "experimenteel" : "");
        }
      });
    };

    showTemp("outside", val.outside);
    showTemp("boiler", val.boiler, boilerLoading ? ["laadt buffer"] : []);
    showTemp("buffer_top", val.buffer_top);
    showTemp("buffer_bottom", val.buffer_bottom);
    showTemp("hot_water", val.hot_water, dhwLoading ? ["laadt"] : []);
    showTemp("hot_water_target", val.hot_water_target, [], "gewenst");
    showTemp("flow", val.flow, heating ? ["circuit actief"] : []);
    const roomPills = [];
    if (val.room_target !== null) roomPills.push(`doel ${fmtTemp(val.room_target)} °C`);
    showTemp("room", val.room, roomPills);

    // mode chip
    const clock = this._state("clock");
    setBoth("mode", (el) => {
      el.classList.toggle("hidden", !this._entityFor("mode"));
      el.classList.toggle("unavailable", !mode || mode === "unavailable");
      const label = MODE_LABELS[mode] || (mode === "unavailable" ? "Geen data" : mode || "—");
      el.querySelector(".value").innerHTML = `<ha-icon icon="${MODE_ICONS[mode] || MODE_ICONS.unknown}"></ha-icon>${esc(label)}`;
      const pills = [];
      if (val.room_target !== null) pills.push(`setpoint ${fmtTemp(val.room_target)} °C`);
      if (clock && clock.state && clock.state !== "unavailable") pills.push(clock.state.replace("T", " ").slice(0, 16));
      el.querySelector(".sub").innerHTML = pills.map((p) => `<span class="pill">${esc(p)}</span>`).join("");
    });

    // flame chip
    setBoth("flame", (el) => {
      el.classList.toggle("hidden", !this._entityFor("flame"));
      el.classList.toggle("on", flameOn === true);
      el.classList.toggle("unavailable", flameOn === null);
      const text = flameOn === null ? "Geen data" : flameOn ? "Warmtevraag" : "Geen vraag";
      el.querySelector(".value").innerHTML = `<ha-icon icon="${flameOn ? "mdi:fire-alert" : "mdi:fire-off"}"></ha-icon>${esc(text)}`;
      const exp = el.querySelector(".exp");
      if (exp) {
        const conf = flameState && flameState.attributes ? flameState.attributes.confidence : "";
        exp.textContent = conf === "candidate" ? "experimenteel · 2004 P19" : flameOn ? "ketel moet leveren" : "";
      }
      const sub = el.querySelector(".sub");
      if (sub && flameOn && flameState) {
        sub.innerHTML = `<span class="pill">sinds ${esc(fmtAge(Date.now() - new Date(flameState.last_changed).getTime()))}</span>`;
      } else if (sub) sub.innerHTML = "";
    });

    // ---- availability / staleness ----
    const main = this._state("boiler") || this._state("outside") || flameState;
    const status = r.querySelector("#status");
    const banner = r.querySelector("#banner");
    let statusText = "live";
    let cls = "";
    let bannerText = "";
    if (!main) {
      cls = "offline"; statusText = "geen entiteit";
      bannerText = "Entiteiten niet gevonden. Controleer de entity-ids in de kaartconfiguratie.";
    } else if (main.state === "unavailable") {
      cls = "offline"; statusText = "offline";
      bannerText = "Geen data van de Gamma: gamma2mqtt is offline of ontvangt geen geldige frames.";
    } else {
      const age = Date.now() - new Date(main.last_updated).getTime();
      if (age > 15 * 60 * 1000) { cls = "stale"; statusText = `laatste update ${fmtAge(age)} geleden`; }
    }
    if (status) { status.className = `status ${cls}`; r.querySelector("#status-text").textContent = statusText; }
    if (banner) { banner.textContent = bannerText; banner.classList.toggle("show", !!bannerText); }
  }

  _toggle(sel, on) {
    const el = this._root.querySelector(sel);
    if (el) el.classList.toggle("on", !!on);
  }
}

if (!customElements.get("froeling-gamma-card")) {
  customElements.define("froeling-gamma-card", FroelingGammaCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "froeling-gamma-card")) {
  window.customCards.push({
    type: "froeling-gamma-card",
    name: "Fröling Gamma kaart",
    description: "Schematisch overzicht van houtketel, buffer, boiler en verwarmingscircuit (EBV Gamma 23 B via gamma2mqtt).",
    preview: true,
  });
}

console.info(`%c FROELING-GAMMA-CARD %c v${CARD_VERSION} `, "background:#ff9a3c;color:#0a1220;font-weight:700", "background:#0a1220;color:#ff9a3c");
