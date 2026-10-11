#!/usr/bin/env python3
"""Passive raw capture of the Gamma bus including 9th-bit (parity) information.

Opens the port as 8S1 and enables termios PARMRK, so every byte whose parity does
not match SPACE (i.e. the MARK-parity slot/scan bytes) arrives as ``FF 00 <byte>``
and a genuine ``FF`` data byte arrives as ``FF FF``. Each read chunk is logged with
a monotonic nanosecond timestamp so slot timing can be reconstructed.

    python3 rawcap.py --port /dev/serial/by-id/... --seconds 480 --out raw.log

Output lines:  <t_ns> <hex bytes of the chunk>
Never writes to the bus.
"""

import argparse
import os
import select
import termios
import time

import serial


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--seconds", type=int, default=480)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ser = serial.Serial(args.port, baudrate=9600, bytesize=8, parity=serial.PARITY_SPACE,
                        stopbits=1, timeout=0)
    fd = ser.fileno()
    attrs = termios.tcgetattr(fd)
    iflag = attrs[0]
    iflag |= termios.INPCK | termios.PARMRK
    iflag &= ~(termios.IGNPAR | termios.ISTRIP)
    attrs[0] = iflag
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    end = time.monotonic() + args.seconds
    chunks = 0
    with open(args.out, "w") as out:
        out.write(f"# start {time.strftime('%Y-%m-%dT%H:%M:%S')} mono_ns {time.monotonic_ns()} port {args.port}\n")
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.5)
            if not r:
                continue
            data = os.read(fd, 4096)
            if data:
                out.write(f"{time.monotonic_ns()} {data.hex()}\n")
                chunks += 1
                if chunks % 200 == 0:
                    out.flush()
        out.write(f"# end {time.strftime('%Y-%m-%dT%H:%M:%S')} mono_ns {time.monotonic_ns()}\n")
    ser.close()
    print("chunks:", chunks, "->", args.out)


if __name__ == "__main__":
    main()
