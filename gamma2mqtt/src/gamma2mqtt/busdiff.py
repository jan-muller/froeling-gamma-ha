"""gamma-busdiff: show which payload bytes change over time in a frames CSV.

Use it to correlate an action on the controller (changing the operating mode,
the flame symbol appearing) with the bytes that moved::

    gamma-busdiff gamma_frames_2026-10-11.csv                # every change, whole file
    gamma-busdiff frames.csv --at 20:31:00 --at 20:33:30     # only +/- window around times
    gamma-busdiff frames.csv --kinds 2806,2004 --window 45

Known always-changing positions (the clock in 0905, the 0100 toggle byte) are
suppressed unless ``--all`` is given. Positions are 1-based Gamma positions.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .model import FIELDS

#: (kind, position) pairs that change continuously and only add noise.
NOISE = {("0905", p) for p in range(3, 11)} | {("0100", 2)}

KNOWN: Dict[Tuple[str, int], str] = {}
for _f in FIELDS:
    _k = (_f.kind, _f.position)
    KNOWN[_k] = (KNOWN[_k] + "/" + _f.key) if _k in KNOWN else _f.key

Key = Tuple[str, str, str, int]  # kind, source, destination, position


def parse_time(text: str, day: datetime) -> datetime:
    """Accept HH:MM, HH:MM:SS or a full ISO timestamp."""
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    parts = [int(x) for x in text.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return day.replace(hour=parts[0], minute=parts[1], second=parts[2], microsecond=0)


def load(path: Path, kinds: Optional[set]) -> List[Tuple[datetime, str, str, str, bytes]]:
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if kinds and row["type"] not in kinds:
                continue
            rows.append((datetime.fromisoformat(row["timestamp"]), row["type"], row["source"],
                         row["destination"], bytes.fromhex(row["payload_hex"])))
    return rows


def changes(rows, include_noise: bool = False):
    """Yield (time, key, old, new) for every byte change, keyed per route."""
    previous: Dict[Key, int] = {}
    for stamp, kind, src, dst, payload in rows:
        for idx, byte in enumerate(payload, start=1):
            if not include_noise and (kind, idx) in NOISE:
                continue
            key = (kind, src, dst, idx)
            old = previous.get(key)
            if old is not None and old != byte:
                yield stamp, key, old, byte
            previous[key] = byte


def describe(key: Key) -> str:
    kind, src, dst, pos = key
    name = KNOWN.get((kind, pos), "")
    return f"{kind} {src}->{dst} P{pos:<3}" + (f" {name}" if name else "")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="gamma-busdiff", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="gamma_frames*.csv file")
    ap.add_argument("--at", action="append", default=[], metavar="TIME",
                    help="HH:MM[:SS] or ISO timestamp of an action; repeatable")
    ap.add_argument("--window", type=float, default=60.0,
                    help="seconds before/after each --at to show (default 60)")
    ap.add_argument("--kinds", default=None, help="comma separated telegram types to include")
    ap.add_argument("--all", action="store_true", help="include clock/toggle noise positions")
    ap.add_argument("--summary", action="store_true",
                    help="only print per-position counts and value sets, no timeline")
    args = ap.parse_args(argv)

    kinds = set(k.strip().upper() for k in args.kinds.split(",")) if args.kinds else None
    rows = load(args.csv, kinds)
    if not rows:
        print("no frames", file=sys.stderr)
        return 1
    first, last = rows[0][0], rows[-1][0]
    print(f"{len(rows)} frames  {first.isoformat(timespec='seconds')} -> {last.isoformat(timespec='seconds')}")

    marks = [parse_time(t, first) for t in args.at]
    windows = [(m - timedelta(seconds=args.window), m + timedelta(seconds=args.window)) for m in marks]

    def in_window(stamp: datetime) -> bool:
        return not windows or any(a <= stamp <= b for a, b in windows)

    counts: Dict[Key, int] = defaultdict(int)
    values: Dict[Key, set] = defaultdict(set)
    timeline = []
    for stamp, key, old, new in changes(rows, args.all):
        if not in_window(stamp):
            continue
        counts[key] += 1
        values[key].update((old, new))
        timeline.append((stamp, key, old, new))

    if not args.summary:
        for m in marks:
            print(f"--- action marker {m.isoformat(timespec='seconds')} (+/- {args.window:.0f}s)")
        current_marker = 0
        for stamp, key, old, new in timeline:
            while current_marker < len(marks) and stamp >= marks[current_marker]:
                print(f"{'=' * 12} >>> {marks[current_marker].strftime('%H:%M:%S')} action <<< {'=' * 12}")
                current_marker += 1
            print(f"{stamp.strftime('%H:%M:%S.%f')[:-3]}  {describe(key):<48} 0x{old:02X} -> 0x{new:02X}  ({old} -> {new})")

    print("\nchanged positions:")
    for key in sorted(counts, key=lambda k: (-counts[k], k)):
        vals = " ".join(f"{v:02X}" for v in sorted(values[key]))
        print(f"  {describe(key):<48} {counts[key]:4d} changes  values: {vals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
