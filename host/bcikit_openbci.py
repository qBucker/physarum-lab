#!/usr/bin/env python3
"""BCIKit M1 (ADS1299) OpenBCI Cyton 8-channel UART logger.

Records the vendor firmware's OpenBCI 33-byte packets at 250 SPS over the
ESP32 UART, writes the raw byte stream, a parsed CSV, meta.json and
SHA256SUMS.

Usage:
    python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode short \
        --duration 300 --outdir data/bench_T1

Notes:
- Single board, 8 channels, 250 SPS (the firmware only allows BCIKit native
  frames over WiFi/BLE; UART is limited to OpenBCI 250 SPS).
- OpenBCI packet: A0 | sample# | 8 x int24 (MSB first) | 6 aux | C0.
- Gain 24 by default (vendor `mode eeg|diff|test|short` profiles).
- The ADS1299 3-byte status word is not present in OpenBCI packets; use the
  BCIKit native protocol over WiFi TCP when status/timestamps are required.
"""

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone

try:
    import serial
except ImportError:  # pragma: no cover
    sys.exit("pyserial is required: pip install pyserial")

PACKET_BYTES = 33
START_BYTE = 0xA0
STOP_BYTE = 0xC0


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def send_command(ser, cmd, wait=0.6):
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode())
    time.sleep(wait)
    return ser.read(8192).decode("utf-8", "replace").strip()


def configure(ser, mode, rate, channels):
    log = {}
    for cmd in ("stop", "boards 1", f"rate {rate}",
                f"channels {channels}", f"mode {mode}", "output openbci"):
        resp = send_command(ser, cmd, 0.8)
        log[cmd] = resp
        if "ERR" in resp or "Failure" in resp:
            raise RuntimeError(f"command failed: {cmd}: {resp}")
    info = send_command(ser, "info", 0.8)
    status = send_command(ser, "status", 0.8)
    log["info"] = info
    log["status"] = status
    if "register_verified=yes" not in status:
        raise RuntimeError("ADS1299 register verification failed:\n" + status)
    return log


def iter_frames(ser, deadline, raw_chunks):
    """Yield complete 33-byte frames, resynchronising on A0..C0."""
    buf = bytearray()
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            raw_chunks.append(chunk)
            buf.extend(chunk)
            while True:
                if len(buf) < PACKET_BYTES:
                    break
                if buf[0] != START_BYTE:
                    idx = buf.find(bytes([START_BYTE]))
                    if idx < 0:
                        buf.clear()
                        break
                    del buf[:idx]
                    continue
                if len(buf) < PACKET_BYTES:
                    break
                if buf[PACKET_BYTES - 1] != STOP_BYTE:
                    del buf[0]
                    continue
                frame = bytes(buf[:PACKET_BYTES])
                del buf[:PACKET_BYTES]
                yield frame


def parse_frame(frame):
    sample = frame[1]
    values = [int.from_bytes(frame[2 + 3 * i:5 + 3 * i], "big", signed=True)
              for i in range(8)]
    return sample, values


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--mode", default="short",
                    choices=["eeg", "diff", "test", "short"])
    ap.add_argument("--rate", type=int, default=250, choices=[250, 500])
    ap.add_argument("--channels", default="0xFF")
    ap.add_argument("--duration", type=float, default=300.0,
                    help="seconds; 0 = until Ctrl+C")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.rate != 250:
        sys.exit("This UART logger supports 250 SPS only (OpenBCI frames at "
                 "115200 baud); 500 SPS needs BCIKit native frames over WiFi.")

    os.makedirs(args.outdir, exist_ok=True)
    raw_path = os.path.join(args.outdir, "raw.bin")
    csv_path = os.path.join(args.outdir, "samples.csv")
    meta_path = os.path.join(args.outdir, "meta.json")

    # A short timeout is required: the USB/IP serial link delivers data in
    # small bursts, and a long timeout lets the kernel tty buffer overflow.
    ser = serial.Serial(args.port, args.baud, timeout=0.01)
    started_at = utc_now()

    setup_log = configure(ser, args.mode, args.rate, args.channels)

    raw_chunks = []
    samples = []
    ser.reset_input_buffer()
    ser.write(b"start\n")
    time.sleep(0.5)
    ser.read(8192)
    t_start = time.time()
    deadline = t_start + args.duration if args.duration > 0 else float("inf")

    try:
        with open(csv_path, "w") as csv:
            csv.write("host_time_iso,host_unix,sample_number," +
                      ",".join(f"ch{i + 1}" for i in range(8)) + "\n")
            for frame in iter_frames(ser, deadline, raw_chunks):
                sample, values = parse_frame(frame)
                now = time.time()
                csv.write(f"{utc_now()},{now:.6f},{sample}," +
                          ",".join(str(v) for v in values) + "\n")
                samples.append(values)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ser.write(b"s")
            time.sleep(0.3)
            ser.read(4096)
        except Exception:
            pass
        ser.close()

    elapsed = time.time() - t_start
    with open(raw_path, "wb") as fh:
        for chunk in raw_chunks:
            fh.write(chunk)

    stats = {}
    if samples:
        for i in range(8):
            col = [row[i] for row in samples]
            stats[f"ch{i + 1}"] = {
                "mean_counts": statistics.mean(col),
                "std_counts": statistics.pstdev(col),
                "min_counts": min(col),
                "max_counts": max(col),
            }

    meta = {
        "label": args.label,
        "note": args.note,
        "mode": args.mode,
        "rate_sps": args.rate,
        "channels": args.channels,
        "port": args.port,
        "baud": args.baud,
        "gain": 24,
        "started_at_utc": started_at,
        "elapsed_s": elapsed,
        "frames": len(samples),
        "effective_sps": (len(samples) / elapsed) if elapsed > 0 else None,
        "host": platform.node(),
        "platform": platform.platform(),
        "firmware_commands": setup_log,
        "channel_stats_counts": stats,
        "notes": [
            "Counts are raw ADS1299 24-bit values at gain 24.",
            "LSB at gain 24, VREF 4.5 V: 4.5/(24*2^23) = 2.235e-8 V.",
            "Full scale at gain 24: +/-4.5/24 = +/-187.5 mV.",
            "OpenBCI packets omit the ADS1299 status word and DRDY timestamp.",
        ],
    }
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)

    sums = []
    for name in ("raw.bin", "samples.csv", "meta.json"):
        path = os.path.join(args.outdir, name)
        sums.append(f"{sha256_file(path)}  {name}")
    with open(os.path.join(args.outdir, "SHA256SUMS"), "w") as fh:
        fh.write("\n".join(sums) + "\n")

    print(f"frames={len(samples)} elapsed={elapsed:.1f}s "
          f"effective_sps={len(samples) / elapsed if elapsed else 0:.2f}")
    for i in range(8):
        s = stats.get(f"ch{i + 1}")
        if s:
            print(f"ch{i + 1}: mean={s['mean_counts']:9.1f} "
                  f"std={s['std_counts']:8.2f} counts")
    print(f"wrote {args.outdir}")


if __name__ == "__main__":
    main()
