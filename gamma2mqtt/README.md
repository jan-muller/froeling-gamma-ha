# gamma2mqtt

Passieve RS485-lezer voor de EBV Gamma 23 B die gedecodeerde waarden via MQTT Discovery in
Home Assistant zet. Verstuurt **nooit** iets op de bus.

## Wat je krijgt in HA

Eén apparaat *Fröling Gamma 23 B* met o.a.:

| Entity | Bron | Betrouwbaarheid |
|---|---|---|
| `sensor.gamma_outside_temperature` | 2004 P2 | bevestigd |
| `sensor.gamma_boiler_temperature` | 2004 P32 | bevestigd (ketel, niet tapwater) |
| `sensor.gamma_heating_flow_temperature` | 1002 P11 | waarschijnlijk (aanvoer na mengkraan) |
| `sensor.gamma_room_temperature` / `_room_target_temperature` | 2806 P2 / P4 | bevestigd |
| `sensor.gamma_room_day_target` / `_room_night_target` | 2806 P37 / P38 | bevestigd |
| `sensor.gamma_hot_water_target` | 2806 P10 | bevestigd, **gewenste** temperatuur |
| `sensor.gamma_operating_mode` | 2806 P7 | bevestigd (`auto`, `heating`, `reduced`, `party`, `absent`, `holiday`, `unknown`) |
| `binary_sensor.gamma_flame_request` | 2004 P19 == 0x01 | **experimenteel** (kandidaat voor vlamsymbool) |
| `sensor.gamma_status_p17_raw`, `_p18_raw`, `_p19_raw` | 2004 | diagnostisch |
| `sensor.gamma_frames_total`, `_crc_errors`, `_frames_per_minute` | bridge | diagnostisch |

Elke entity heeft attributen `confidence`, `telegram`, `position`, `source`, `raw` en `updated`.
Als er `--stale-timeout` seconden geen geldig frame binnenkomt gaat `gamma2mqtt/availability` naar
`offline` en worden alle entiteiten *unavailable* (nooit een valse OFF).

## Installatie op de Raspberry Pi

```bash
sudo apt install python3-venv git
git clone <deze repo> ~/froeling-gamma-ha
cd ~/froeling-gamma-ha/gamma2mqtt
python3 -m venv .venv && .venv/bin/pip install .
ls -l /dev/serial/by-id/            # stabiel poortpad opzoeken
sudo fuser -v /dev/ttyUSB0          # niets anders mag de adapter open hebben
.venv/bin/gamma2mqtt --port /dev/serial/by-id/usb-FTDI_... --mqtt-host <ha-ip> --mqtt-user mqtt --mqtt-password ...
```

Als dienst: zie `gamma2mqtt.service` en `gamma2mqtt.env.example` (het pad in `ExecStart` aanpassen
als de venv ergens anders staat).

## Opties

Alle opties zijn ook beschikbaar als omgevingsvariabele `GAMMA_<OPTIE>`:

```
--port, --mqtt-host, --mqtt-port, --mqtt-user, --mqtt-password, --mqtt-client-id
--topic-prefix (gamma2mqtt)  --discovery-prefix (homeassistant)  --device-id (gamma23b)
--stale-timeout 60  --republish-interval 300  --expire-after 900
--publish-raw            # elke frame-payload onder gamma2mqtt/raw/<type>
--replay CSV --replay-speed N --replay-loop   # capture afspelen i.p.v. seriële poort
--print-discovery        # discovery-payloads tonen en stoppen
```

## Testen zonder hardware

```bash
uv sync --extra dev && uv run pytest
uv run gamma2mqtt --replay "../GAMMA_23B_COMPLEET_CLAUDE_PAKKET/gamma_frames(3).csv" \
    --replay-speed 20 --replay-loop --mqtt-host <broker>
```

De replay publiceert exact dezelfde topics als de live service; handig om de dashboardkaart te bouwen.

## Topics

```
gamma2mqtt/availability            online|offline (retained, LWT)
gamma2mqtt/<key>/state             entity state (retained)
gamma2mqtt/<key>/attributes        JSON
gamma2mqtt/bridge/state            JSON met frames_total, crc_errors, frames_per_minute, frame_kinds
homeassistant/<component>/gamma23b/<key>/config
```
