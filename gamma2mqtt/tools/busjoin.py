#!/usr/bin/env python3
"""Step B experiment: answer the Gamma's presence poll for a free bus address.

The Gamma (master) polls addresses with the 9th bit set (``*22`` = byte 0x22 with
MARK parity). A room unit answers its poll with ``<addr> 06`` (plain SPACE-parity
bytes). This script does exactly that for ``--address`` and NOTHING else: it never
sends frames or setpoints. Everything received and sent is logged with timestamps
so the Gamma's reaction (tokens, 0100 telegrams) can be analysed with rawanalyze.py.

    python3 busjoin.py --port /dev/serial/by-id/... --address 0x22 --seconds 180 --out join.log

Stop at any time with Ctrl+C; the port is closed and the Gamma simply sees the
device disappear, as it does for any absent room unit.
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
    ap.add_argument("--address", type=lambda x: int(x, 0), default=0x22)
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-replies", type=int, default=50, help="safety cap on replies sent")
    ap.add_argument("--delay-ms", type=float, default=2.5,
                    help="wait this long after the poll before replying (room unit: ~2.5 ms)")
    ap.add_argument("--gap-ms", type=float, default=1.9,
                    help="idle time between the bytes we send (bus convention: ~1.9 ms)")
    ap.add_argument("--ack", action="store_true",
                    help="answer a CRC-valid frame that follows our poll reply with 06")
    ap.add_argument("--on-token", default=None, metavar="HEX",
                    help="payload to send as a frame <addr>->10 when we receive a *90 token after "
                         "our poll reply, e.g. '02 10' (the 0102 read request). Default: none")
    ap.add_argument("--announce", default=None, metavar="HEX",
                    help="payload of a 0100 frame <addr>->AA to send right after acking the frame "
                         "that follows our poll reply, e.g. '00 01'. Default: none")
    ap.add_argument("--reply", default="06 {addr}",
                    help="bytes to send on a poll, hex, {addr} = our address (default: '06 {addr}')")
    args = ap.parse_args()

    ser = serial.Serial(args.port, baudrate=9600, bytesize=8, parity=serial.PARITY_SPACE,
                        stopbits=1, timeout=0, write_timeout=0.2)
    try:
        ser.set_low_latency_mode(True)  # FTDI latency timer 16 ms -> 1 ms
    except Exception as exc:  # noqa: BLE001
        print("low latency mode not set:", exc)
    fd = ser.fileno()
    attrs = termios.tcgetattr(fd)
    attrs[0] = (attrs[0] | termios.INPCK | termios.PARMRK) & ~(termios.IGNPAR | termios.ISTRIP)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    reply = bytes.fromhex(args.reply.replace("{addr}", f"{args.address:02x}"))

    def send(data: bytes) -> None:
        for k, b in enumerate(data):
            if k and args.gap_ms > 0:
                time.sleep(args.gap_ms / 1000.0)
            ser.write(bytes([b]))
            ser.flush()

    def frame(src: int, dst: int, payload: bytes) -> bytes:
        body = bytes([src, dst, len(payload) - 1]) + payload
        return bytes([0x82]) + body + crc16(body).to_bytes(2, "little") + bytes([0x03])

    def crc16(d: bytes) -> int:
        crc = 0
        for byte in d:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
        return crc
    end = time.monotonic() + args.seconds
    replies = 0
    acks = 0
    pending = b""
    selected_until = 0.0  # after our poll reply, watch for a frame to ack
    rxframe = bytearray()
    token_until = 0.0
    tokens = 0
    on_token = bytes.fromhex(args.on_token) if args.on_token else None
    announce = bytes.fromhex(args.announce) if args.announce else None
    with open(args.out, "w") as out:
        out.write(f"# start {time.strftime('%Y-%m-%dT%H:%M:%S')} mono_ns {time.monotonic_ns()} "
                  f"port {args.port} address 0x{args.address:02X}\n")
        try:
            while time.monotonic() < end:
                r, _, _ = select.select([fd], [], [], 0.5)
                if not r:
                    continue
                data = os.read(fd, 4096)
                if not data:
                    continue
                out.write(f"{time.monotonic_ns()} {data.hex()}\n")
                # Decode PARMRK on the fly to spot a marked poll for our address.
                buf = pending + data
                pending = b""
                i = 0
                polled = False
                while i < len(buf):
                    if buf[i] == 0xFF:
                        if i + 1 >= len(buf):
                            pending = buf[i:]
                            break
                        if buf[i + 1] == 0xFF:
                            i += 2
                            continue
                        if buf[i + 1] == 0x00:
                            if i + 2 >= len(buf):
                                pending = buf[i:]
                                break
                            if buf[i + 2] == args.address:
                                polled = True
                            elif buf[i + 2] == 0x21:
                                token_until = 0.0  # never answer tokens during the room unit's turn
                            elif buf[i + 2] == 0x90 and on_token is not None and time.monotonic() < token_until:
                                send(b"\x06\x90")
                                time.sleep(args.gap_ms / 1000.0)
                                fr = frame(args.address, 0x10, on_token)
                                send(fr)
                                tokens += 1
                                out.write(f"{time.monotonic_ns()} TX 0690{fr.hex()}\n")
                                print(time.strftime("%H:%M:%S"), f"token *90 -> sent 06 90 + {fr.hex(' ')} (#{tokens})", flush=True)
                                selected_until = time.monotonic() + 0.5  # ack the answer frame
                            rxframe.clear()
                            i += 3
                            continue
                    if args.ack and time.monotonic() < selected_until:
                        rxframe.append(buf[i])
                        start = rxframe.find(0x82)
                        if start >= 0 and len(rxframe) - start >= 4:
                            size = rxframe[start + 3] + 8
                            if len(rxframe) - start >= size:
                                cand = bytes(rxframe[start:start + size])
                                if cand[-1] == 0x03 and crc16(cand[1:-3]) == int.from_bytes(cand[-3:-1], "little"):
                                    time.sleep(0.0012)
                                    send(b"\x06")
                                    acks += 1
                                    out.write(f"{time.monotonic_ns()} TX 06\n")
                                    print(time.strftime("%H:%M:%S"), f"frame {cand[1]:02X}->{cand[2]:02X} {cand[4:-3].hex(' ')} -> acked (#{acks})", flush=True)
                                    if announce is not None and cand[2] == 0xAA:
                                        time.sleep(args.gap_ms / 1000.0)
                                        fr = frame(args.address, 0xAA, announce)
                                        send(fr)
                                        out.write(f"{time.monotonic_ns()} TX {fr.hex()}\n")
                                        print(time.strftime("%H:%M:%S"), f"announced {fr.hex(' ')}", flush=True)
                                    token_until = time.monotonic() + 6.0
                                rxframe.clear()
                    i += 1
                if polled and replies < args.max_replies:
                    if args.delay_ms > 0:
                        time.sleep(args.delay_ms / 1000.0)
                    send(reply)
                    selected_until = time.monotonic() + 0.5
                    replies += 1
                    out.write(f"{time.monotonic_ns()} TX {reply.hex()}\n")
                    out.flush()
                    print(time.strftime("%H:%M:%S"), f"poll *{args.address:02X} -> replied {reply.hex(' ')} (#{replies})", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            out.write(f"# end {time.strftime('%Y-%m-%dT%H:%M:%S')} mono_ns {time.monotonic_ns()} replies {replies} acks {acks} tokens {tokens}\n")
    ser.close()
    print("replies sent:", replies, "->", args.out)


if __name__ == "__main__":
    main()
