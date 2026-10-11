"""Gamma RS485 frame layer: CRC-16/KERMIT and a streaming frame parser.

Pure Python, no I/O, so it can be unit-tested with captured frames.

Frame layout (all bytes on the wire, 9600 8S1)::

    82 SRC DST LL PAYLOAD[LL + 1] CRC_LO CRC_HI 03

* ``LL`` is the length field; the payload holds ``LL + 1`` bytes.
* ``PAYLOAD[0]`` is the subtype. The telegram *kind* is ``f"{LL:02X}{PAYLOAD[0]:02X}"``
  (for example ``2004`` or ``1002``).
* CRC-16/KERMIT over ``SRC DST LL PAYLOAD`` (not over ``82``, the CRC or ``03``),
  stored little-endian.
* Total frame length is ``LL + 8``.

Gamma field positions in documentation are 1-based (``P1`` is the subtype byte);
use :meth:`Frame.p` to avoid off-by-one errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

START = 0x82
END = 0x03
#: All documented payloads have LL <= 0x80, so LL + 8 <= 136.
MAX_FRAME = 136
MIN_FRAME = 8


def crc16_kermit(data: Iterable[int]) -> int:
    """CRC-16/KERMIT: init 0x0000, reflected poly 0x8408, xorout 0x0000."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


@dataclass(frozen=True)
class Frame:
    source: int
    destination: int
    payload: bytes
    raw: bytes

    @property
    def kind(self) -> str:
        """Telegram type such as ``2004`` (length field + subtype, upper-case hex)."""
        return f"{len(self.payload) - 1:02X}{self.payload[0]:02X}"

    def p(self, position: int) -> Optional[int]:
        """1-based payload position (``P1`` == ``payload[0]``). ``None`` if absent."""
        if 1 <= position <= len(self.payload):
            return self.payload[position - 1]
        return None

    @property
    def route(self) -> str:
        return f"{self.source:02X}->{self.destination:02X}"

    @classmethod
    def parse(cls, raw: bytes) -> Optional["Frame"]:
        """Validate a complete candidate frame (including ``82`` and ``03``)."""
        if len(raw) < MIN_FRAME or raw[0] != START or raw[-1] != END:
            return None
        if len(raw) != raw[3] + 8:
            return None
        expected = int.from_bytes(raw[-3:-1], "little")
        if crc16_kermit(raw[1:-3]) != expected:
            return None
        return cls(source=raw[1], destination=raw[2], payload=bytes(raw[4:-3]), raw=bytes(raw))

    @classmethod
    def build(cls, source: int, destination: int, payload: bytes) -> "Frame":
        """Construct a valid frame (used by tests and the replay tooling only; the
        bridge never transmits on the bus)."""
        body = bytes([source, destination, len(payload) - 1]) + payload
        crc = crc16_kermit(body)
        raw = bytes([START]) + body + crc.to_bytes(2, "little") + bytes([END])
        return cls(source=source, destination=destination, payload=bytes(payload), raw=raw)


class FrameParser:
    """Incremental parser that resynchronises on the byte stream.

    Feed arbitrary chunks with :meth:`feed`; complete CRC-valid frames are returned.
    Bytes between frames (``FF`` idle bytes, slot markers) are skipped. A ``0x82``
    that does not start a valid frame is dropped and scanning continues one byte later.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.rejected = 0  # candidate frames with bad CRC / terminator
        self.skipped_bytes = 0  # bytes discarded while searching for a start byte

    def feed(self, data: bytes) -> List[Frame]:
        self.buffer.extend(data)
        frames: List[Frame] = []
        while True:
            start = self.buffer.find(bytes([START]))
            if start < 0:
                self.skipped_bytes += len(self.buffer)
                self.buffer.clear()
                break
            if start:
                self.skipped_bytes += start
                del self.buffer[:start]
            if len(self.buffer) < 4:
                break
            size = self.buffer[3] + 8
            if size > MAX_FRAME:
                del self.buffer[0]
                self.skipped_bytes += 1
                continue
            if len(self.buffer) < size:
                break
            frame = Frame.parse(bytes(self.buffer[:size]))
            if frame is None:
                self.rejected += 1
                del self.buffer[0]
                continue
            del self.buffer[:size]
            frames.append(frame)
        return frames
