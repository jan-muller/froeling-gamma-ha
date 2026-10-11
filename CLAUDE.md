# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two independent deliverables that together bring a Fröling wood boiler + EBV Gamma 23 B heating
controller into Home Assistant, fully local:

1. `gamma2mqtt/` – Python service for the Raspberry Pi. Reads the Gamma RS485 bus **passively**
   (9600 8S1), validates CRC-16/KERMIT frames, decodes known payload bytes and publishes them with
   MQTT Discovery. Never transmits on the bus; do not add writes or any boiler control.
2. `froeling-gamma-card/` – dependency-free Lovelace custom card (single JS file, no build step)
   that draws the installation as an SVG schematic with the live values overlaid.

`GAMMA_23B_COMPLEET_CLAUDE_PAKKET/` is reference material, not code to maintain: the protocol
handoff document (`GAMMA_23B_HOME_ASSISTANT_HANDOFF.md`, the authoritative source for frame
layout, field positions and confidence levels), CSV captures and the original discovery scripts.
Read the handoff before changing anything in `model.py`. Capture `gamma_frames(2).csv` is the long
"flame symbol off" recording, `gamma_frames(3).csv` the short "flame symbol on" one; tests rely on
them being present.

## Commands

```bash
# Python service (run from gamma2mqtt/)
uv sync --extra dev                 # creates .venv with pytest
uv run pytest                       # all tests (use real captured frames)
uv run pytest tests/test_decode.py -k p19   # single test
uv run gamma2mqtt --print-discovery # dump HA discovery payloads
uv run gamma2mqtt --replay "../GAMMA_23B_COMPLEET_CLAUDE_PAKKET/gamma_frames(3).csv" \
    --replay-speed 20 --replay-loop --mqtt-host <broker>   # end-to-end without hardware
```

The card has no tooling: open `froeling-gamma-card/dev/preview.html` in a browser (it mocks
`hass` with values from the captures and has scenario buttons). Verify visual changes with a
screenshot of that page; no console errors is the bar.

## Architecture notes

**gamma2mqtt pipeline** (`src/gamma2mqtt/`): `sources.py` (serial or CSV replay, both expose
`read()`) → `protocol.py` (`FrameParser.feed()` resyncs on the byte stream, `Frame.p(n)` is the
1-based Gamma position) → `decode.py` (applies the `FIELDS` table) → `bridge.py` (change detection,
periodic republish, availability watchdog, MQTT) with `discovery.py` generating HA configs from the
same `FIELDS` table. Adding a decoded value therefore means one new `Field` in `model.py` plus a
test; discovery and publishing follow automatically.

Conventions that matter:
- Field positions are 1-based (`P1` is the subtype byte). `Frame.p()` and the `half()/outside()/...`
  helpers already handle this; never index `payload[pos]` directly.
- Every `Field` carries a `confidence` (`confirmed` / `probable` / `candidate` / `raw`) that is
  published as an entity attribute and shown by the card. Keep it honest; the flame request
  (`2004 P19`) stays `candidate` until a live display transition has been logged.
- `2806` is sent by two bus addresses with different bytes; fields from it are pinned to
  `source=CONTROLLER (0x10)`. Any per-field history must key on `(kind, source, destination, P)`.
- Stale data makes entities *unavailable* (bridge availability topic + `expire_after`), never OFF.
- `bridge.py` supports both paho-mqtt 1.x (Debian packages on the Pi) and 2.x; keep both paths.

**Card** (`froeling-gamma-card/dist/froeling-gamma-card.js`): the SVG scene in `sceneSvg()` uses a
1000×560 viewBox and the `CHIPS` array positions the HTML value chips in the same coordinate space;
move both together. Chip DOM classes are `chip-<id>` (plain `<id>` clashes with SVG classes such
as `.flow`). Animations are driven purely by toggling `.on`; derived activity (heating circuit,
boiler loading) is computed in `_update()` from thresholds or optional pump entities and should
stay conservative. Default entity ids match what gamma2mqtt creates (`sensor.gamma_<key>`).

## Language

User-facing text (entity names, card labels, READMEs, commit messages) is Dutch; code, identifiers
and MQTT keys are English.
