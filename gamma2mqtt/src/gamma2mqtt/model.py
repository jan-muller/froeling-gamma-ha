"""Field table: which payload bytes we decode and how they appear in Home Assistant.

One :class:`Field` per Home Assistant entity. ``decode.py`` uses the ``kind``,
``source`` and ``convert`` columns; ``discovery.py`` uses the HA metadata.

Confidence levels (mirrors the handoff document, keep them honest):

* ``confirmed``  – value matches external documentation and our own readings.
* ``probable``   – strong correlation in our captures, not independently verified.
* ``candidate``  – distinguishes the captured situations but no live transition seen.
* ``raw``        – undocumented byte exposed for diagnostics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

#: Operating mode codes from the external RS10 protocol mapping.
MODES: Dict[int, str] = {
    0x00: "auto",
    0x03: "heating",
    0x04: "reduced",
    0x13: "party",
    0x14: "absent",
    0x24: "holiday",
}

#: Gamma controller address that carries the authoritative 2806 room block.
#: 2806 is also sent by 0x21 with partially different bytes (P20/P21).
CONTROLLER = 0x10


def _bcd(value: Optional[int]) -> Optional[int]:
    if value is None or (value >> 4) > 9 or (value & 15) > 9:
        return None
    return (value >> 4) * 10 + (value & 15)


def half(pos: int) -> Callable[[bytes], Optional[float]]:
    return lambda p: p[pos - 1] / 2 if len(p) >= pos else None


def outside(pos: int) -> Callable[[bytes], Optional[float]]:
    return lambda p: p[pos - 1] / 2 - 52 if len(p) >= pos else None


def raw_hex(pos: int) -> Callable[[bytes], Optional[str]]:
    return lambda p: f"0x{p[pos - 1]:02X}" if len(p) >= pos else None


def mode(pos: int) -> Callable[[bytes], Optional[str]]:
    return lambda p: MODES.get(p[pos - 1], "unknown") if len(p) >= pos else None


def flag(pos: int, on: int = 0x01) -> Callable[[bytes], Optional[bool]]:
    return lambda p: (p[pos - 1] == on) if len(p) >= pos else None


def dhw_reload(pos: int) -> Callable[[bytes], Optional[str]]:
    table = {0: "off", 1: "requested", 2: "active"}
    return lambda p: table.get(p[pos - 1], "unknown") if len(p) >= pos else None


def controller_datetime(p: bytes) -> Optional[str]:
    """0905 telegram: BCD seconds/minutes/hours at P3..P5, day P6, year P8, month P10."""
    if len(p) < 10:
        return None
    sec, minute, hour = _bcd(p[2]), _bcd(p[3]), _bcd(p[4])
    day, year, month = _bcd(p[5]), _bcd(p[7]), _bcd(p[9])
    if None in (sec, minute, hour, day, year, month):
        return None
    if not (sec < 60 and minute < 60 and hour < 24 and 1 <= day <= 31 and 1 <= month <= 12):
        return None
    return f"20{year:02d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{sec:02d}"


@dataclass(frozen=True)
class Field:
    key: str
    kind: str
    position: int
    convert: Callable[[bytes], Any]
    name: str
    confidence: str
    component: str = "sensor"
    source: Optional[int] = None  # restrict to this bus address; None = any
    unit: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    icon: Optional[str] = None
    diagnostic: bool = False
    enabled: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def position_label(self) -> str:
        return f"{self.kind} P{self.position}"


def _temp(key: str, kind: str, pos: int, name: str, confidence: str, **kw: Any) -> Field:
    kw.setdefault("convert", half(pos))
    return Field(
        key=key, kind=kind, position=pos, name=name, confidence=confidence,
        unit="°C", device_class="temperature", state_class="measurement", **kw,
    )


FIELDS: Tuple[Field, ...] = (
    # --- 2004: outside/boiler temperature and status bytes (10 -> 20, ~1/s) ---
    _temp("outside_temperature", "2004", 2, "Buitentemperatuur", "confirmed",
          convert=outside(2)),
    _temp("boiler_temperature", "2004", 32, "Keteltemperatuur", "confirmed"),
    Field("flame_request", "2004", 19, flag(19), "Aansteekvraag (experimenteel)", "candidate",
          component="binary_sensor", icon="mdi:fire", extra={"device_class": None}),
    Field("status_p17_raw", "2004", 17, raw_hex(17), "2004 P17 (raw)", "raw",
          diagnostic=True, icon="mdi:hexadecimal"),
    Field("status_p18_raw", "2004", 18, raw_hex(18), "2004 P18 (raw)", "raw",
          diagnostic=True, icon="mdi:hexadecimal"),
    Field("status_p19_raw", "2004", 19, raw_hex(19), "2004 P19 (raw)", "raw",
          diagnostic=True, icon="mdi:hexadecimal"),
    Field("status_p33_raw", "2004", 33, raw_hex(33), "2004 P33 (raw)", "raw",
          diagnostic=True, icon="mdi:hexadecimal", enabled=False),
    # --- 1002: short data block answering the 0102 request (10 -> 20, ~1/5s) ---
    _temp("heating_flow_temperature", "1002", 11, "Aanvoertemperatuur (na mengkraan)", "probable"),
    _temp("boiler_temperature_2", "1002", 12, "Keteltemperatuur (1002)", "confirmed",
          diagnostic=True, enabled=False),
    _temp("outside_temperature_2", "1002", 7, "Buitentemperatuur (1002)", "probable",
          diagnostic=True, enabled=False),
    Field("status_1002_p13_raw", "1002", 13, raw_hex(13), "1002 P13 (raw)", "raw",
          diagnostic=True, icon="mdi:hexadecimal", enabled=False),
    # --- 2806: room unit / setpoints / mode (10 -> 20 authoritative) ---
    _temp("room_temperature", "2806", 2, "Kamertemperatuur", "confirmed", source=CONTROLLER),
    _temp("room_target_temperature", "2806", 4, "Kamer setpoint actief", "confirmed",
          source=CONTROLLER),
    _temp("room_day_target", "2806", 37, "Kamer setpoint dag", "confirmed", source=CONTROLLER),
    _temp("room_night_target", "2806", 38, "Kamer setpoint nacht", "confirmed",
          source=CONTROLLER),
    _temp("hot_water_target", "2806", 10, "Warmwater setpoint", "confirmed", source=CONTROLLER,
          icon="mdi:water-thermometer"),
    Field("operating_mode", "2806", 7, mode(7), "Bedrijfsmodus", "confirmed",
          source=CONTROLLER, device_class="enum", icon="mdi:home-thermometer",
          extra={"options": sorted(set(MODES.values())) + ["unknown"]}),
    Field("hot_water_manual_reload", "2806", 11, dhw_reload(11), "Warmwater nalading", "probable",
          source=CONTROLLER, device_class="enum", icon="mdi:water-boiler",
          extra={"options": ["off", "requested", "active", "unknown"]}, diagnostic=True),
    # --- 0905: controller clock ---
    Field("controller_time", "0905", 3, controller_datetime, "Regelaar klok", "confirmed",
          diagnostic=True, icon="mdi:clock-outline", enabled=False),
)

FIELDS_BY_KEY: Dict[str, Field] = {f.key: f for f in FIELDS}
