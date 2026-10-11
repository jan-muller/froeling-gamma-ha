"""Turn validated frames into named readings using the field table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .model import FIELDS, Field
from .protocol import Frame


@dataclass(frozen=True)
class Reading:
    field: Field
    value: Any
    raw: int
    frame: Frame

    @property
    def key(self) -> str:
        return self.field.key


_INDEX: Dict[str, Tuple[Field, ...]] = {}
for _f in FIELDS:
    _INDEX.setdefault(_f.kind, ())
    _INDEX[_f.kind] = _INDEX[_f.kind] + (_f,)


def decode(frame: Frame) -> List[Reading]:
    """Decode every field defined for ``frame.kind`` (and matching source)."""
    readings: List[Reading] = []
    for f in _INDEX.get(frame.kind, ()):
        if f.source is not None and frame.source != f.source:
            continue
        value = f.convert(frame.payload)
        if value is None:
            continue
        raw = frame.p(f.position)
        readings.append(Reading(field=f, value=value, raw=raw if raw is not None else -1, frame=frame))
    return readings
