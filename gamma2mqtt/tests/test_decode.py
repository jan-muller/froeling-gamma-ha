import csv
from collections import Counter

from gamma2mqtt.decode import decode
from gamma2mqtt.model import FIELDS, FIELDS_BY_KEY
from gamma2mqtt.protocol import Frame

from test_protocol import F0905, F1002, F2004_FLAME, F2004_NOFLAME, F2806_10


def by_key(frame):
    return {r.key: r.value for r in decode(Frame.parse(frame))}


def test_2004_flame_on():
    v = by_key(F2004_FLAME)
    assert v["outside_temperature"] == 0x81 / 2 - 52 == 12.5
    assert v["boiler_temperature"] == 36.0
    assert v["flame_request"] is True
    assert v["status_p17_raw"] == "0x62"
    assert v["status_p18_raw"] == "0x10"
    assert v["status_p19_raw"] == "0x01"


def test_2004_flame_off():
    v = by_key(F2004_NOFLAME)
    assert v["outside_temperature"] == 8.5
    assert v["boiler_temperature"] == 73.0
    assert v["flame_request"] is False


def test_1002():
    v = by_key(F1002)
    assert v["outside_temperature_2"] == 12.5
    assert v["heating_flow_temperature"] == 26.5
    assert v["boiler_temperature_2"] == 36.0
    assert v["status_1002_p13_raw"] == "0x24"


def test_2806_from_controller_only():
    v = by_key(F2806_10)
    assert v["room_temperature"] == 22.0
    assert v["room_target_temperature"] == 23.0
    assert v["operating_mode"] == "auto"
    assert v["hot_water_target"] == 55.0
    assert v["room_day_target"] == 21.0
    assert v["room_night_target"] == 16.0
    assert v["hot_water_manual_reload"] == "off"
    # Same payload from the second bus participant (0x21) must be ignored.
    other = Frame.build(0x21, 0x20, Frame.parse(F2806_10).payload)
    assert decode(other) == []


def test_0905_clock():
    v = by_key(F0905)
    assert v["controller_time"] == "2026-10-11T14:41:31"


def test_unknown_mode_is_unknown():
    payload = bytearray(Frame.parse(F2806_10).payload)
    payload[6] = 0x77
    v = {r.key: r.value for r in decode(Frame.build(0x10, 0x20, bytes(payload)))}
    assert v["operating_mode"] == "unknown"


def test_field_keys_unique():
    keys = [f.key for f in FIELDS]
    assert len(keys) == len(set(keys))
    assert FIELDS_BY_KEY["flame_request"].component == "binary_sensor"


def test_p19_separates_captures(captures_dir):
    """Reproduce the handoff claim: P19 == 0 in the long capture, 1 in the flame capture."""
    expected = {"gamma_frames(2).csv": {False: 14647}, "gamma_frames(3).csv": {True: 70}}
    for name, want in expected.items():
        c = Counter()
        with (captures_dir / name).open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row["type"] != "2004":
                    continue
                frame = Frame.parse(bytes.fromhex(row["frame_hex"]))
                c[by_key(frame.raw)["flame_request"]] += 1
        assert dict(c) == want, name
