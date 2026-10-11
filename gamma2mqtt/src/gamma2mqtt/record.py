"""Optional frame recorder: appends every valid frame to a daily CSV.

Schema matches the capture tooling so the files can be replayed (``--replay``)
and analysed (``gamma-busdiff``)::

    timestamp,type,source,destination,payload_length,payload_hex,frame_hex
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from .protocol import Frame

log = logging.getLogger(__name__)

HEADER = ["timestamp", "type", "source", "destination", "payload_length", "payload_hex", "frame_hex"]


class FrameRecorder:
    def __init__(self, directory: str, flush_interval: float = 5.0) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.flush_interval = flush_interval
        self._fh: Optional[TextIO] = None
        self._writer = None
        self._day: Optional[str] = None
        self._last_flush = time.monotonic()
        self.rows = 0

    def _path_for(self, day: str) -> Path:
        return self.directory / f"gamma_frames_{day}.csv"

    def _open(self, day: str) -> None:
        self.close()
        path = self._path_for(day)
        new = not path.exists() or path.stat().st_size == 0
        self._fh = path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        if new:
            self._writer.writerow(HEADER)
        self._day = day
        log.info("Recording frames to %s", path)

    def write(self, frame: Frame, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        day = now.strftime("%Y-%m-%d")
        if day != self._day:
            self._open(day)
        assert self._writer is not None
        self._writer.writerow([
            now.isoformat(timespec="milliseconds"), frame.kind,
            f"{frame.source:02X}", f"{frame.destination:02X}",
            len(frame.payload), frame.payload.hex(" "), frame.raw.hex(" "),
        ])
        self.rows += 1
        if time.monotonic() - self._last_flush >= self.flush_interval:
            self.flush()

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()
        self._last_flush = time.monotonic()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None
            self._writer = None
            self._day = None
