import csv

from gamma2mqtt.protocol import Frame, FrameParser, crc16_kermit

# Frames taken verbatim from the captures (flame symbol ON, 11 Oct 2026 14:53).
F2004_FLAME = bytes.fromhex(
    "82 10 20 20 04 81 10 00 00 00 00 00 00 00 00 00 00 00 00 00 62 10 01 10"
    " 00 00 00 00 00 00 00 00 00 10 01 48 4c 16 cb 03")
F2004_NOFLAME = bytes.fromhex(
    "82 10 20 20 04 79 10 00 00 00 00 00 00 00 00 00 00 00 00 00 62 10 00 10"
    " 00 00 00 00 00 00 00 00 00 00 00 92 4c 07 9a 03")
F1002 = bytes.fromhex("82 10 20 10 02 00 ff 00 00 00 19 00 00 00 35 48 24 00 00 00 2c 80 62 03")
F2806_10 = bytes.fromhex(
    "82 10 20 28 06 2c 02 2e aa 00 00 81 00 6e 00 00 00 00 41 00 0b 00 01 11 2a 20 00 00 00"
    " 00 02 00 2a 20 00 00 00 00 01 00 2a 20 00 00 00 7a d2 03")
F0905 = bytes.fromhex("82 10 20 09 05 00 31 41 14 11 a6 26 07 10 d0 bc 03")
F0100 = bytes.fromhex("82 10 aa 01 00 01 86 81 03")


def test_crc_kermit_known_vector():
    assert crc16_kermit(b"123456789") == 0x2189


def test_parse_valid_frames():
    for raw in (F2004_FLAME, F2004_NOFLAME, F1002, F2806_10, F0905, F0100):
        frame = Frame.parse(raw)
        assert frame is not None, raw.hex()
        assert len(raw) == raw[3] + 8
    f = Frame.parse(F2004_FLAME)
    assert f.kind == "2004"
    assert f.source == 0x10 and f.destination == 0x20
    assert f.p(1) == 0x04  # subtype is P1
    assert f.p(2) == 0x81
    assert f.p(19) == 0x01
    assert f.p(32) == 0x48
    assert f.p(33) == 0x4C
    assert f.p(34) is None


def test_parse_rejects_bad_crc_and_terminator():
    bad = bytearray(F1002)
    bad[6] ^= 0x01
    assert Frame.parse(bytes(bad)) is None
    bad = bytearray(F1002)
    bad[-1] = 0x00
    assert Frame.parse(bytes(bad)) is None


def test_build_roundtrip():
    f = Frame.build(0x10, 0x20, F1002[4:-3])
    assert f.raw == F1002


def test_parser_resyncs_on_noise_and_chunking():
    stream = b"\xff\xff\x82\x01" + F2004_FLAME + b"\xfc\x82" + F1002 + b"\xff" + F2806_10
    parser = FrameParser()
    frames = []
    for i in range(0, len(stream), 5):  # feed in tiny chunks
        frames.extend(parser.feed(stream[i:i + 5]))
    assert [f.kind for f in frames] == ["2004", "1002", "2806"]
    assert parser.rejected >= 1


def test_parser_handles_0x82_inside_payload():
    # Payload containing 0x82 must not confuse resync once the real frame is complete.
    payload = bytes([0x04]) + bytes([0x82] * 32)
    f = Frame.build(0x10, 0x20, payload)
    parser = FrameParser()
    out = parser.feed(b"\x82" + f.raw)  # leading stray start byte
    assert len(out) == 1 and out[0].raw == f.raw


def test_all_captured_frames_parse(captures_dir):
    """Every row of the short flame capture must parse and match its CSV fields."""
    parser = FrameParser()
    with (captures_dir / "gamma_frames(3).csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    stream = b"".join(bytes.fromhex(r["frame_hex"]) for r in rows)
    frames = parser.feed(stream)
    assert len(frames) == len(rows) == 247
    assert parser.rejected == 0
    for row, frame in zip(rows, frames):
        assert frame.kind == row["type"]
        assert frame.source == int(row["source"], 16)
        assert frame.payload.hex(" ") == row["payload_hex"]
