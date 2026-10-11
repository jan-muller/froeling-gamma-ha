# gamma2mqtt

Passive RS485 reader for the EBV Gamma 23 B that publishes decoded values to Home Assistant via
MQTT Discovery. It **never** transmits on the bus.

## What you get in HA

One device *Fröling Gamma 23 B* with, among others:

| Entity | Source | Confidence |
|---|---|---|
| `sensor.gamma_outside_temperature` | 2004 P2 | confirmed |
| `sensor.gamma_boiler_temperature` | 2004 P32 | confirmed (boiler, not domestic hot water) |
| `sensor.gamma_heating_flow_temperature` | 1002 P11 | probable (flow after the mixing valve) |
| `sensor.gamma_room_temperature` / `_room_target_temperature` | 2806 P2 / P4 | confirmed |
| `sensor.gamma_room_day_target` / `_room_night_target` | 2806 P37 / P38 | confirmed |
| `sensor.gamma_hot_water_target` | 2806 P10 | confirmed, **setpoint** only |
| `sensor.gamma_operating_mode` | 2806 P7 | confirmed (`auto`, `heating`, `reduced`, `party`, `absent`, `holiday`, `unknown`) |
| `binary_sensor.gamma_flame_request` | 2004 P19 == 0x01 | **experimental** (candidate for the flame symbol) |
| `sensor.gamma_status_p17_raw`, `_p18_raw`, `_p19_raw` | 2004 | diagnostic |
| `sensor.gamma_frames_total`, `_crc_errors`, `_frames_per_minute` | bridge | diagnostic |

Every entity carries the attributes `confidence`, `telegram`, `position`, `source`, `raw` and
`updated`. When no valid frame arrives for `--stale-timeout` seconds, `gamma2mqtt/availability`
goes `offline` and all entities become *unavailable* (never a false OFF).

## Installation on the Raspberry Pi

```bash
sudo apt install python3-venv git
git clone https://github.com/jan-muller/froeling-gamma-ha.git ~/froeling-gamma-ha
cd ~/froeling-gamma-ha/gamma2mqtt
python3 -m venv .venv && .venv/bin/pip install .
ls -l /dev/serial/by-id/            # find the stable port path
sudo fuser -v /dev/ttyUSB0          # nothing else may hold the adapter open
.venv/bin/gamma2mqtt --port /dev/serial/by-id/usb-FTDI_... --mqtt-host <ha-ip> --mqtt-user mqtt --mqtt-password ...
```

To run as a service see `gamma2mqtt.service` and `gamma2mqtt.env.example` (adjust the path in
`ExecStart` if the venv lives elsewhere).

## Options

Every option is also available as an environment variable `GAMMA_<OPTION>`:

```
--port, --mqtt-host, --mqtt-port, --mqtt-user, --mqtt-password, --mqtt-client-id
--topic-prefix (gamma2mqtt)  --discovery-prefix (homeassistant)  --device-id (gamma23b)
--stale-timeout 60  --republish-interval 300  --expire-after 900
--publish-raw            # every frame payload under gamma2mqtt/raw/<type>
--replay CSV --replay-speed N --replay-loop   # replay a capture instead of the serial port
--print-discovery        # print the discovery payloads and exit
```

## Testing without hardware

```bash
uv sync --extra dev && uv run pytest
uv run gamma2mqtt --replay path/to/gamma_frames.csv \
    --replay-speed 20 --replay-loop --mqtt-host <broker>
```

The replay takes a `gamma_frames*.csv` file as written by the capture tooling (columns
`timestamp,type,source,destination,payload_length,payload_hex,frame_hex`) and publishes exactly the
same topics as the live service, which is convenient for developing the dashboard card.
Tests that need captures look for them in a gitignored `private/` folder in the repository root and
skip when it is absent.

## Topics

```
gamma2mqtt/availability            online|offline (retained, LWT)
gamma2mqtt/<key>/state             entity state (retained)
gamma2mqtt/<key>/attributes        JSON
gamma2mqtt/bridge/state            JSON with frames_total, crc_errors, frames_per_minute, frame_kinds
homeassistant/<component>/gamma23b/<key>/config
```
