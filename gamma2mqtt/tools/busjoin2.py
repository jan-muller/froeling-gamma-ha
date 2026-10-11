#!/usr/bin/env python3
"""Bus-join experiment, strict state machine.

We only ever transmit inside our own slot: from the Gamma's poll of our address
(``*<addr>``) until the next marked byte that is not a ``*90`` token. A marked
``*21`` (the room unit's poll) or a frame announcement (``*FF``/``*FC``) always
returns us to IDLE, so we can never collide with the room unit's turn.

States
  IDLE       listen; on ``*<addr>`` send ``06 <addr>`` -> SELECTED
  SELECTED   expect a frame from the master; on CRC-valid frame send ``06``,
             optionally send our own announce frame (``0100 <addr>->AA``) -> SLOT
  SLOT       on ``*90`` token send ``06 90`` + request frame -> ANSWER
             on any other marked byte -> IDLE
  ANSWER     expect the master's reply frame; ack it with ``06`` -> SLOT

    python3 busjoin2.py --port ... --address 0x22 --seconds 100 --out x.log \
        [--announce "00 01"] [--on-token "02 10"] [--max-tokens 1]
"""

import argparse
import os
import select
import termios
import time

import serial

GAP = 0.0019  # idle time between bytes we send (bus convention ~1.9 ms)


def crc16(d: bytes) -> int:
    crc = 0
    for byte in d:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


def frame(src: int, dst: int, payload: bytes) -> bytes:
    body = bytes([src, dst, len(payload) - 1]) + payload
    return bytes([0x82]) + body + crc16(body).to_bytes(2, "little") + bytes([0x03])


class Joiner:
    def __init__(self, ser, out, address, announce, on_token, max_tokens, max_replies):
        self.ser, self.out, self.addr = ser, out, address
        self.announce, self.on_token = announce, on_token
        self.max_tokens, self.max_replies = max_tokens, max_replies
        self.state = "IDLE"
        self.registered = False   # we answered our address poll at least once
        self.blocked = False      # room unit's turn in progress: never answer *90
        self.answer_90 = False
        self.last_reply_at = 0.0
        self.last_poll_at = 0.0
        self.skip_first = False
        self.ack_delay = 0.0012
        self.prefix = b""
        self.preack = -1.0
        self.preacked = False
        self.mirror_2806 = False
        self.last_2806 = None     # latest 2806 payload seen from the room unit (21->20)
        self.pbuf = bytearray()   # passive frame parser over everything we hear
        self.mirrors = self.mirror_acks = 0
        self.deadline = 0.0
        self.rx = bytearray()
        self.tokens_this_slot = 0
        self.replies = self.acks = self.tokens = self.announces = 0

    def log(self, text):
        print(time.strftime("%H:%M:%S"), text, flush=True)

    def send(self, data: bytes, label: str):
        if self.prefix:
            data = self.prefix + data
        for k, b in enumerate(data):
            if k:
                time.sleep(GAP)
            self.ser.write(bytes([b]))
            self.ser.flush()
        self.out.write(f"{time.monotonic_ns()} TX {data.hex()}\n")
        self.out.flush()
        self.log(f"[{self.state}] TX {label}: {data.hex(' ')}")

    def to(self, state, timeout=0.6):
        self.state = state
        self.deadline = time.monotonic() + timeout
        self.rx.clear()

    def marked(self, b: int):
        if b in (0xFF, 0xFC):
            self.blocked = False  # broadcast markers: a new cycle starts
        if b == 0x21:
            self.blocked = True
        if b == self.addr:
            # one presence reply per cycle: ignore the trailing *addr x5 polls after our turn
            now = time.monotonic()
            if now < self.last_reply_at + 2.5:
                return
            if self.skip_first and now - self.last_poll_at > 0.2:
                self.last_poll_at = now  # the room unit ignores the first poll, answers the second
                return
            self.last_poll_at = now
            if self.state == "IDLE" and self.replies < self.max_replies:
                self.last_reply_at = time.monotonic()
                self.replies += 1
                self.registered = True
                self.tokens_this_slot = 0
                self.send(bytes([0x06, self.addr]), "poll reply")
                self.to("SELECTED")
            return
        if (b == 0x90 and self.state == "IDLE" and self.answer_90 and self.registered
                and not self.blocked and self.replies < self.max_replies):
            self.replies += 1
            self.tokens_this_slot = 0
            self.send(b"\x06\x90", "cycle-start 90 reply")
            self.to("SELECTED")
            return
        if b == 0x90 and self.state == "SLOT":
            if self.on_token is not None and self.tokens_this_slot < self.max_tokens:
                self.tokens_this_slot += 1
                self.tokens += 1
                self.send(b"\x06\x90" + frame(self.addr, 0x10, self.on_token), "token reply")
                self.to("ANSWER")
            return
        # any other marked byte ends our slot
        if self.state != "IDLE":
            self.log(f"[{self.state}] marked *{b:02X} -> IDLE")
            self.to("IDLE", 0)

    def passive(self, b: int):
        self.pbuf.append(b)
        if len(self.pbuf) > 300:
            del self.pbuf[:-150]
        start = self.pbuf.find(0x82)
        if start < 0 or len(self.pbuf) - start < 4:
            return
        size = self.pbuf[start + 3] + 8
        if len(self.pbuf) - start < size:
            return
        cand = bytes(self.pbuf[start:start + size])
        if cand[-1] == 0x03 and crc16(cand[1:-3]) == int.from_bytes(cand[-3:-1], "little"):
            if cand[1] == 0x21 and cand[2] == 0x20 and cand[3] == 0x28 and cand[4] == 0x06:
                self.last_2806 = cand[4:-3]
            del self.pbuf[:start + size]
        else:
            del self.pbuf[:start + 1]

    def data(self, b: int):
        self.passive(b)
        if self.state == "SENT":
            if b == 0x06:
                self.mirror_acks += 1
                self.log(f"[SENT] master acked our 2806 (#{self.mirror_acks})")
                self.to("SLOT", 4.0)
            return
        if self.state not in ("SELECTED", "ANSWER"):
            return
        self.rx.append(b)
        start = self.rx.find(0x82)
        if start < 0 or len(self.rx) - start < 4:
            return
        size = self.rx[start + 3] + 8
        if self.preack >= 0 and len(self.rx) - start == size - 1:
            # Pre-emptive ack: CRC is complete, only the 0x03 terminator is still on the wire.
            cand = bytes(self.rx[start:start + size - 1])
            if crc16(cand[1:-2]) == int.from_bytes(cand[-2:], "little"):
                self.rx.clear()
                self.preacked = True
                time.sleep(self.preack)
                cand = cand + b"\x03"
                self._ack_and_continue(cand)
            return
        if len(self.rx) - start < size:
            return
        cand = bytes(self.rx[start:start + size])
        self.rx.clear()
        if self.preacked:
            self.preacked = False
            return
        if cand[-1] != 0x03 or crc16(cand[1:-3]) != int.from_bytes(cand[-3:-1], "little"):
            return
        if self.ack_delay > 0:
            time.sleep(self.ack_delay)
        self._ack_and_continue(cand)

    def _ack_and_continue(self, cand: bytes):
        self.acks += 1
        self.send(b"\x06", f"ack {cand[1]:02X}->{cand[2]:02X} {cand[4:-3].hex(' ')[:40]}")
        if self.state == "SELECTED" and self.announce is not None:
            time.sleep(GAP)
            self.announces += 1
            self.send(frame(self.addr, 0xAA, self.announce), "announce")
        if self.state == "SELECTED" and self.mirror_2806 and self.last_2806 is not None:
            time.sleep(GAP)
            self.mirrors += 1
            self.send(frame(self.addr, 0x20, self.last_2806), f"mirror 2806 (P7={self.last_2806[6]:02X} P12={self.last_2806[11]:02X})")
            self.to("SENT", 0.6)
            return
        self.to("SLOT", 4.0)

    def tick(self):
        if self.state != "IDLE" and time.monotonic() > self.deadline:
            self.log(f"[{self.state}] timeout -> IDLE")
            self.to("IDLE", 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--address", type=lambda x: int(x, 0), default=0x22)
    ap.add_argument("--seconds", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--announce", default=None, help="payload of 0100 <addr>->AA after our ack, hex")
    ap.add_argument("--on-token", default=None, help="payload of request <addr>->10 on a *90 token, hex")
    ap.add_argument("--max-tokens", type=int, default=1)
    ap.add_argument("--mirror-2806", action="store_true",
                    help="after acking the link frame, send a 2806 <addr>->20 identical to the room unit's latest block")
    ap.add_argument("--ack-delay-ms", type=float, default=1.2,
                    help="wait before acking a frame (default 1.2 ms; 0 = as fast as possible)")
    ap.add_argument("--preack-ms", type=float, default=-1.0,
                    help="send the ack this many ms after the CRC arrives, before the 03 terminator (-1 = off)")
    ap.add_argument("--prefix", default=None, metavar="HEX",
                    help="byte(s) to prepend to every transmission (test: does the master drop our first byte?)")
    ap.add_argument("--skip-first", action="store_true",
                    help="answer the second poll of our address, not the first (as the room unit does)")
    ap.add_argument("--answer-90", action="store_true",
                    help="after registering, answer the cycle-start *90 burst with 06 90 (like a poll)")
    ap.add_argument("--max-replies", type=int, default=40)
    args = ap.parse_args()

    ser = serial.Serial(args.port, baudrate=9600, bytesize=8, parity=serial.PARITY_SPACE,
                        stopbits=1, timeout=0, write_timeout=0.2)
    ser.set_low_latency_mode(True)
    fd = ser.fileno()
    attrs = termios.tcgetattr(fd)
    attrs[0] = (attrs[0] | termios.INPCK | termios.PARMRK) & ~(termios.IGNPAR | termios.ISTRIP)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    end = time.monotonic() + args.seconds
    pending = b""
    with open(args.out, "w") as out:
        out.write(f"# start {time.strftime('%Y-%m-%dT%H:%M:%S')} mono_ns {time.monotonic_ns()} port {args.port} address 0x{args.address:02X}\n")
        j = Joiner(ser, out, args.address,
                   bytes.fromhex(args.announce) if args.announce else None,
                   bytes.fromhex(args.on_token) if args.on_token else None,
                   args.max_tokens, args.max_replies)
        j.answer_90 = args.answer_90
        j.mirror_2806 = args.mirror_2806
        j.skip_first = args.skip_first
        j.ack_delay = args.ack_delay_ms / 1000.0
        j.prefix = bytes.fromhex(args.prefix) if args.prefix else b""
        j.preack = args.preack_ms / 1000.0 if args.preack_ms >= 0 else -1.0
        try:
            while time.monotonic() < end:
                r, _, _ = select.select([fd], [], [], 0.05)
                j.tick()
                if not r:
                    continue
                raw = os.read(fd, 4096)
                if not raw:
                    continue
                out.write(f"{time.monotonic_ns()} {raw.hex()}\n")
                buf = pending + raw
                pending = b""
                i = 0
                while i < len(buf):
                    b = buf[i]
                    if b == 0xFF:
                        if i + 1 >= len(buf):
                            pending = buf[i:]
                            break
                        if buf[i + 1] == 0xFF:
                            j.data(0xFF)
                            i += 2
                            continue
                        if buf[i + 1] == 0x00:
                            if i + 2 >= len(buf):
                                pending = buf[i:]
                                break
                            j.marked(buf[i + 2])
                            i += 3
                            continue
                    j.data(b)
                    i += 1
        except KeyboardInterrupt:
            pass
        finally:
            out.write(f"# end {time.strftime('%Y-%m-%dT%H:%M:%S')} replies {j.replies} acks {j.acks} announces {j.announces} tokens {j.tokens} mirrors {j.mirrors} mirror_acks {j.mirror_acks}\n")
    ser.close()
    print(f"replies {j.replies} acks {j.acks} announces {j.announces} tokens {j.tokens} mirrors {j.mirrors} mirror_acks {j.mirror_acks} -> {args.out}")


if __name__ == "__main__":
    main()
