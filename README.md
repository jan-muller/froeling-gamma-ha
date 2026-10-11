# froeling-gamma-ha

Fröling FH-G Turbo 2000 wood boiler + EBV Gamma 23 B heating controller → Home Assistant, fully local, no cloud.

| Directory | What |
|---|---|
| [`gamma2mqtt/`](gamma2mqtt) | Python service for the Raspberry Pi: reads the Gamma passively over RS485 (9600 8S1), validates CRC-16/KERMIT, decodes the known fields and publishes them via MQTT Discovery. |
| [`dist/froeling-gamma-card.js`](dist) + [`froeling-gamma-card/`](froeling-gamma-card) | Lovelace card (HACS) with a schematic view of the boiler, buffer tank, hot-water cylinder and heating circuit, with live values placed where they belong. The card file lives in `dist/` and `hacs.json` in the root because HACS requires that layout; docs, example config and the dev preview are in `froeling-gamma-card/`. |

Data flow: `Gamma 23 B ──RS485──> Pi (gamma2mqtt) ──MQTT──> Home Assistant ──> froeling-gamma-card`

![card preview](docs/card-preview.png)

Safety: this project only reads. No RS485 writes, no boiler control based on provisionally
interpreted status bytes. The ignition request (`2004 P19`) is a candidate until a live transition
of the flame symbol on the display has been logged.
