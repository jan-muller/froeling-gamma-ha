#!/usr/bin/env python3
"""Analyse a rawcap.py log: decode PARMRK 9th-bit markers, find CRC-valid frames,
show which marked bytes precede/follow each frame and dump one bus cycle.

    python3 rawanalyze.py raw.log
"""
import sys, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

path = sys.argv[1]
lines = open(path).read().splitlines()
m = re.match(r"# start (\S+) mono_ns (\d+)", lines[0])
start_wall = datetime.fromisoformat(m.group(1)); start_ns = int(m.group(2))
def wall(ns): return start_wall + timedelta(microseconds=(ns-start_ns)/1000)

# token stream: (t_ns, byte, marked)
stream = []
pending = b""
for ln in lines[1:]:
    if ln.startswith("#"): continue
    parts = ln.split()
    if len(parts) == 3 and parts[1] == "TX":
        for b in bytes.fromhex(parts[2]):
            stream.append((int(parts[0]), b, False, True))
        continue
    t, hx = parts
    t = int(t); data = pending + bytes.fromhex(hx); pending = b""
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0xFF:
            if i + 1 >= len(data): pending = data[i:]; break
            if data[i+1] == 0xFF: stream.append((t, 0xFF, False, False)); i += 2; continue
            if data[i+1] == 0x00:
                if i + 2 >= len(data): pending = data[i:]; break
                stream.append((t, data[i+2], True, False)); i += 3; continue
        stream.append((t, b, False, False)); i += 1

print("bytes:", len(stream), "marked:", sum(1 for s in stream if s[2]), "tx:", sum(1 for s in stream if s[3]))
print("marked values:", Counter(f"{b:02X}" for _, b, mk, _tx in stream if mk).most_common(20))

def crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8): crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc

# frames over unmarked bytes (keep index into stream)
frames = []  # (idx_start, idx_end, src, dst, kind, payload)
i = 0
n = len(stream)
while i < n:
    if stream[i][1] == 0x82 and not stream[i][2] and i + 4 <= n:
        ll = stream[i+3][1]; size = ll + 8
        if i + size <= n:
            cand = bytes(s[1] for s in stream[i:i+size])
            if cand[-1] == 0x03 and crc16(cand[1:-3]) == int.from_bytes(cand[-3:-1], "little") and not any(s[2] or s[3] for s in stream[i:i+size]):
                pl = cand[4:-3]
                frames.append((i, i+size, cand[1], cand[2], f"{ll:02X}{pl[0]:02X}", pl))
                i += size; continue
    i += 1
print("frames:", len(frames), Counter((f"{f[2]:02X}->{f[3]:02X}", f[4]) for f in frames).most_common())

# What precedes each frame? collect the last 6 tokens before frame start (marked flagged with *)
pre = defaultdict(Counter)
gaps = defaultdict(list)
for (a, b, src, dst, kind, pl) in frames:
    ctx = stream[max(0, a-6):a]
    desc = " ".join((">" if tx else "*" if mk else "") + f"{by:02X}" for _, by, mk, tx in ctx)
    pre[(f"{src:02X}", kind)][desc] += 1
    # gap from last marked byte to frame start
    j = a - 1
    while j >= 0 and not stream[j][2]: j -= 1
    if j >= 0:
        gaps[(f"{src:02X}", kind)].append((stream[a][0] - stream[j][0]) / 1e6)
print("\n=== preceding tokens per (src, kind) ===")
for k in sorted(pre):
    print(k)
    for d, c in pre[k].most_common(4): print(f"   {c:5d}  ...{d}")
    g = sorted(gaps[k])
    if g: print(f"   gap last-marked->frame ms: min {g[0]:.1f} med {g[len(g)//2]:.1f} max {g[-1]:.1f}")

# What follows frames? tokens after frame end
post = defaultdict(Counter)
for (a, b, src, dst, kind, pl) in frames:
    ctx = stream[b:b+5]
    post[(f"{src:02X}", kind)][" ".join((">" if tx else "*" if mk else "") + f"{by:02X}" for _, by, mk, tx in ctx)] += 1
print("\n=== following tokens ===")
for k in sorted(post):
    print(k, post[k].most_common(3))

# timeline of 2806 P7 changes + the full token sequence around the first 21->20 2806 with P7 change
prev = {}
print("\n=== 2806 P7 / P12 changes ===")
for (a, b, src, dst, kind, pl) in frames:
    if kind == "2806":
        key = src
        v = (pl[6], pl[11])
        if prev.get(key) != v:
            print(wall(stream[a][0]).strftime("%H:%M:%S.%f")[:-3], f"{src:02X}->{dst:02X} P7=0x{pl[6]:02X} P12=0x{pl[11]:02X}")
            prev[key] = v

# Dump a full cycle: ~600 ms of tokens around one 21->20 2806 frame (first one after 20:37:40)
target = None
for (a, b, src, dst, kind, pl) in frames:
    if kind == "2806" and src == 0x21 and wall(stream[a][0]) >= datetime.fromisoformat("2026-10-11T20:37:40"):
        target = (a, b); break
if target:
    a, b = target
    t0 = stream[a][0]
    print("\n=== token dump around 21->20 2806 at", wall(t0).strftime("%H:%M:%S.%f")[:-3], "(ms rel, * = 9th bit set) ===")
    lo = a
    while lo > 0 and stream[a][0] - stream[lo][0] < 1.2e9: lo -= 1
    hi = b
    while hi < n and stream[hi][0] - stream[a][0] < 0.6e9: hi += 1
    # group consecutive tokens with same timestamp chunk
    cur_t = None; buf = []
    def flush():
        if buf: print(f"{(cur_t - t0)/1e6:9.1f} ms  " + " ".join(buf))
    for t, by, mk, tx in stream[lo:hi]:
        if t != cur_t:
            flush(); cur_t = t; buf = []
        buf.append((">" if tx else "*" if mk else "") + f"{by:02X}")
    flush()

tx_idx = [k for k, s_ in enumerate(stream) if s_[3]]
if tx_idx:
    print("\n=== context around TX replies (first 4, ms rel to TX; > = sent by us) ===")
    shown = 0; last = -10**18
    for k in tx_idx:
        if stream[k][0] - last < 2e9: continue
        last = stream[k][0]; shown += 1
        if shown > 4: break
        t0 = stream[k][0]
        lo = k
        while lo > 0 and t0 - stream[lo][0] < 0.4e9: lo -= 1
        hi = k
        while hi < n and stream[hi][0] - t0 < 1.5e9: hi += 1
        print(f"--- TX at {wall(t0).strftime('%H:%M:%S.%f')[:-3]}")
        cur_t = None; buf = []
        for t, by, mk, tx in stream[lo:hi]:
            if t != cur_t:
                if buf: print(f"{(cur_t - t0)/1e6:9.1f} ms  " + " ".join(buf))
                cur_t = t; buf = []
            buf.append((">" if tx else "*" if mk else "") + f"{by:02X}")
        if buf: print(f"{(cur_t - t0)/1e6:9.1f} ms  " + " ".join(buf))
