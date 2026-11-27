#!/usr/bin/env python3
"""BCIKit M1 (ADS1299) OpenBCI Cyton 8-channel UART logger.

Records the vendor firmware's OpenBCI 33-byte packets at 250 SPS over the
ESP32 UART, writes the raw byte stream, a parsed CSV, meta.json and
SHA256SUMS. The recorder streams raw.bin to disk and keeps online channel
statistics, so memory stays constant for multi-hour runs.

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
import math
import os
import platform
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


def iter_frames(ser, deadline, on_chunk=None):
    """Yield complete 33-byte frames, resynchronising on A0..C0.

    Every serial chunk is passed to ``on_chunk`` exactly as received, so the
    caller can stream the raw byte log to disk without retaining it.
    """
    buf = bytearray()
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            if on_chunk is not None:
                on_chunk(chunk)
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


class ChannelStats:
    """Online per-channel mean, population std, min and max (Welford)."""

    def __init__(self, n_channels=8):
        self.n = 0
        self.mean = [0.0] * n_channels
        self.m2 = [0.0] * n_channels
        self.vmin = [None] * n_channels
        self.vmax = [None] * n_channels

    def update(self, values):
        self.n += 1
        n = self.n
        for i, v in enumerate(values):
            delta = v - self.mean[i]
            self.mean[i] += delta / n
            self.m2[i] += delta * (v - self.mean[i])
            if self.vmin[i] is None or v < self.vmin[i]:
                self.vmin[i] = v
            if self.vmax[i] is None or v > self.vmax[i]:
                self.vmax[i] = v

    def summary_counts(self):
        out = {}
        if self.n == 0:
            return out
        for i in range(len(self.mean)):
            out[f"ch{i + 1}"] = {
                "mean_counts": self.mean[i],
                "std_counts": math.sqrt(max(self.m2[i] / self.n, 0.0)),
                "min_counts": self.vmin[i],
                "max_counts": self.vmax[i],
            }
        return out


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
    ap.add_argument("--progress-every", type=float, default=60.0,
                    help="seconds between progress lines; 0 disables")
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
    ser = serial.Serial(args.port, args.baud, timeout=0.01,
                        dsrdtr=False, rtscts=False)
    started_at = utc_now()

    # Opening a Windows COM port toggles DTR/RTS and resets the ESP32.
    # Wait for the firmware to boot before configuring or reading status.
    time.sleep(1.5)
    ser.reset_input_buffer()

    setup_log = configure(ser, args.mode, args.rate, args.channels)

    channel_stats = ChannelStats()
    frame_count = 0
    run_error = None
    ser.reset_input_buffer()
    ser.write(b"start\n")
    time.sleep(0.5)
    ser.read(8192)
    t_start = time.time()
    deadline = t_start + args.duration if args.duration > 0 else float("inf")
    end_status = ""
    last_progress = t_start

    raw_fh = open(raw_path, "wb")
    try:
        with open(csv_path, "w") as csv:
            csv.write("host_time_iso,host_unix,sample_number," +
                      ",".join(f"ch{i + 1}" for i in range(8)) + "\n")
            for frame in iter_frames(ser, deadline, raw_fh.write):
                sample, values = parse_frame(frame)
                now = time.time()
                csv.write(f"{utc_now()},{now:.6f},{sample}," +
                          ",".join(str(v) for v in values) + "\n")
                channel_stats.update(values)
                frame_count += 1
                if args.progress_every > 0 and now - last_progress >= args.progress_every:
                    elapsed_now = now - t_start
                    print(f"progress frames={frame_count} "
                          f"elapsed={elapsed_now:.0f}s "
                          f"sps={frame_count / elapsed_now:.2f}", flush=True)
                    raw_fh.flush()
                    last_progress = now
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        print(f"run error: {run_error}", file=sys.stderr, flush=True)
    finally:
        try:
            ser.write(b"s")
            time.sleep(0.3)
            ser.read(4096)
            end_status = send_command(ser, "status", 0.8)
        except Exception:
            pass
        ser.close()
        raw_fh.flush()
        raw_fh.close()

    elapsed = time.time() - t_start
    stats_counts = channel_stats.summary_counts()

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
        "frames": frame_count,
        "effective_sps": (frame_count / elapsed) if elapsed > 0 else None,
        "host": platform.node(),
        "platform": platform.platform(),
        "firmware_commands": setup_log,
        "device_status_start": setup_log.get("status", ""),
        "device_status_end": end_status,
        "channel_stats_counts": stats_counts,
        "run_error": run_error,
        "notes": [
            "Counts are raw ADS1299 24-bit values at gain 24.",
            "LSB at gain 24, VREF 4.5 V: 4.5/(24*2^23) = 2.235e-8 V.",
            "Full scale at gain 24: +/-4.5/24 = +/-187.5 mV.",
            "OpenBCI packets omit the ADS1299 status word and DRDY timestamp.",
            "Recorder streams raw.bin and keeps online channel statistics; "
            "memory is constant during the run.",
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

    print(f"frames={frame_count} elapsed={elapsed:.1f}s "
          f"effective_sps={frame_count / elapsed if elapsed else 0:.2f}")
    for i in range(8):
        s = stats_counts.get(f"ch{i + 1}")
        if s:
            print(f"ch{i + 1}: mean={s['mean_counts']:9.1f} "
                  f"std={s['std_counts']:8.2f} counts")
    print(f"wrote {args.outdir}")


if __name__ == "__main__":
    main()
