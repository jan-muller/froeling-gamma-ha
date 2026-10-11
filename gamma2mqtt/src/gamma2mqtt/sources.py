"""Byte sources for the bridge: a real serial port or a CSV replay.

Both expose ``read() -> bytes`` (blocking up to a short timeout, may return ``b""``)
and are context managers. The bridge never writes to the bus.
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)


class SerialSource:
    """9600 8S1 passive serial reader with reconnect on failure."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.2) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def open(self) -> None:
        import serial  # imported lazily so tests/replay work without pyserial

        self._ser = serial.Serial(
            self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_SPACE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        log.info("Serial port %s open (%d 8S1)", self.port, self.baudrate)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def read(self) -> bytes:
        if self._ser is None:
            raise OSError("serial port not open")
        return self._ser.read(512)

    def __enter__(self) -> "SerialSource":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class ReplaySource:
    """Replay the ``frame_hex`` column of a ``gamma_frames*.csv`` capture.

    Frames are emitted with the original inter-frame delays divided by ``speed``.
    With ``loop=True`` the file restarts when exhausted, which is handy for
    developing the dashboard card without hardware.
    """

    def __init__(self, path: str, speed: float = 1.0, loop: bool = False) -> None:
        self.path = Path(path)
        self.speed = max(speed, 0.001)
        self.loop = loop
        self._iter: Optional[Iterator[bytes]] = None
        self.finished = False

    def _rows(self) -> Iterator[bytes]:
        while True:
            previous: Optional[datetime] = None
            with self.path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    stamp = datetime.fromisoformat(row["timestamp"])
                    if previous is not None:
                        delay = (stamp - previous).total_seconds() / self.speed
                        if 0 < delay < 30:
                            time.sleep(delay)
                    previous = stamp
                    yield bytes.fromhex(row["frame_hex"])
            if not self.loop:
                return
            log.info("Replay restarting from beginning of %s", self.path.name)

    def open(self) -> None:
        self._iter = self._rows()
        log.info("Replaying %s at %gx speed%s", self.path, self.speed, " (loop)" if self.loop else "")

    def close(self) -> None:
        self._iter = None

    def read(self) -> bytes:
        if self._iter is None:
            raise OSError("replay not open")
        try:
            return next(self._iter)
        except StopIteration:
            self.finished = True
            time.sleep(0.2)
            return b""

    def __enter__(self) -> "ReplaySource":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
