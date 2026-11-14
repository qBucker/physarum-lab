#!/usr/bin/env python3
"""BCIKit native (Raw Stream v1) receiver over WiFi TCP.

The ESP32 runs a WiFi AP (open network `OpenBCI-XXXX`, 192.168.4.1) with an
HTTP control server. The host:

  1. joins that AP and starts a TCP listener,
  2. POSTs {"ip": <host>, "port": <listener>, "output": "bcikit"} to
     http://192.168.4.1/tcp -- the device then connects OUT to the host,
  3. sends BCIKit COMMAND frames over that TCP session to configure and start,
  4. receives SAMPLE frames (55 B for 1 board): 32-bit sequence, 64-bit DRDY
     timestamp, flags, CRC-16/CCITT-FALSE.

Output (per run directory):
  raw_frames.bin   exact SAMPLE wire frames (audit source)
  samples.csv      host_unix,seq,timestamp_us,flags,rate,gain,status,ch01..chN
  meta.json        config, command/ACK log, device info/status, statistics
  SHA256SUMS       hashes of the three files above

Usage (run where the device can reach the listener):
  python host/bcikit_native.py --outdir data/native_test --duration 600
  python host/bcikit_native.py --outdir data/native_run --profile diff --rate 250

With WSL2 NAT, run it from Windows Python instead (device cannot reach WSL):
  D:\\phy\\python.exe "\\\\wsl.localhost\\Ubuntu\\path\\to\\physarum-lab\\host\\bcikit_native.py" --outdir D:\\physarum-data\\native_test --duration 600

Operational notes
-----------------
- The board AP has NO internet. While the laptop is on it, the machine is
  offline. Plan 48 h runs as unattended/offline sessions.
- WSL2 default (NAT) cannot receive the device's outbound connection: run
  this script with Windows Python, or switch WSL to mirrored networking.
  Command channel and listener must be on the same host IP.
- Windows Defender may ask to allow Python on the first listen; allow it on
  the private network.
- BLE is not used here. If BCIKit Studio owns a BLE session, the device may
  reject the WiFi session as BUSY -- disconnect Studio first.
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import socket
import struct
import sys
import time
import urllib.request
from datetime import datetime, timezone

SYNC = b"\xa5\x5a"
PROTOCOL_VERSION = 1

T_SAMPLE = 0x01
T_INFO = 0x02
T_STATUS = 0x03
T_ACK = 0x04
T_EVENT = 0x05
T_COMMAND = 0x80

CMD_GET_INFO = 0x01
CMD_GET_STATUS = 0x02
CMD_START = 0x03
CMD_STOP = 0x04
CMD_SET_OUTPUT = 0x05
CMD_SET_RATE = 0x06
CMD_SET_BOARDS = 0x07
CMD_SET_PROFILE = 0x08
CMD_SET_MASK = 0x09
CMD_RESET_STATS = 0x0A
CMD_PING = 0x0B

PROFILES = {"eeg": 0, "diff": 1, "test": 2, "short": 3}
PROFILE_NAMES = {v: k for k, v in PROFILES.items()}

FLAG_TIME_VALID = 1 << 0
FLAG_DROPPED_BEFORE = 1 << 1
FLAG_REGISTER_VERIFIED = 1 << 2
FLAG_TEST_SIGNAL = 1 << 3
FLAG_INPUT_SHORT = 1 << 4

BYTES_PER_BOARD = 27
SAMPLE_HEADER = 26  # sync..payload_len, exclusive of payload and CRC
LSB_MV = 22.3517e-6  # 4.5 V / (24 * 2**23) in mV/count


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def u16(b, o):
    return b[o] | (b[o + 1] << 8)


def u32(b, o):
    return int.from_bytes(b[o:o + 4], "little")


def u64(b, o):
    return int.from_bytes(b[o:o + 8], "little")


def s24(b, o):
    v = (b[o] << 16) | (b[o + 1] << 8) | b[o + 2]
    return v - 0x1000000 if v & 0x800000 else v


def crc16_ccitt_false(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def command_frame(request_id, command, payload=b""):
    head = (bytes([0xA5, 0x5A, PROTOCOL_VERSION, T_COMMAND]) +
            struct.pack("<I", request_id) + bytes([command, 0]) +
            struct.pack("<H", len(payload)) + payload)
    return head + struct.pack("<H", crc16_ccitt_false(head[2:]))


def sample_payload_len(frame):
    return u16(frame, 24)


def decode_sample(frame):
    flags = u16(frame, 4)
    seq = u32(frame, 6)
    ts = u64(frame, 10)
    rate = u16(frame, 18)
    boards = frame[20]
    gain = frame[22]
    plen = sample_payload_len(frame)
    payload = frame[SAMPLE_HEADER:SAMPLE_HEADER + plen]
    blocks = []
    for i in range(boards):
        blk = payload[i * BYTES_PER_BOARD:(i + 1) * BYTES_PER_BOARD]
        if len(blk) < BYTES_PER_BOARD:
            break
        blocks.append((blk[:3], [s24(blk, 3 + 3 * j) for j in range(8)]))
    blocks.reverse()  # wire order -> physical order
    return {
        "flags": flags, "seq": seq, "ts_us": ts, "rate": rate,
        "boards": boards, "gain": gain,
        "status": [s.hex() for s, _ in blocks],
        "channels": [v for _, ch in blocks for v in ch],
    }


def decode_control_payload(frame):
    plen = u16(frame, 10)
    return frame[12:12 + plen]


def decode_info(frame):
    p = decode_control_payload(frame)
    return {
        "firmware": "%d.%d.%d" % (p[0], p[1], p[2]),
        "protocol": p[3], "hardware_type": p[4],
        "capabilities": u32(p, 5), "max_boards": p[9],
        "rate_mask": p[10], "output_mask": p[11],
        "serial_baud": u32(p, 12), "device_id": u64(p, 16),
    }


def decode_status(frame):
    p = decode_control_payload(frame)
    return {
        "state": p[0], "output": p[1],
        "profile": PROFILE_NAMES.get(p[2], p[2]), "boards": p[3],
        "rate": u16(p, 4), "gain": p[6], "channel_mask": p[7],
        "register_verified": bool(p[8]), "ads_id": p[9],
        "next_seq": u32(p, 10), "uptime_us": u64(p, 14),
        "counters": [u32(p, 22 + 4 * i) for i in range(8)],
    }


class Stats:
    def __init__(self):
        self.frames = 0
        self.gap_events = 0
        self.missing = 0
        self.crc_errors = 0
        self.resyncs = 0
        self.dropped_flag = 0
        self.invalid_time = 0
        self.first_seq = None
        self.last_seq = None
        self.first_ts = None
        self.last_ts = None
        self.first_host = None
        self.last_host = None
        self.flags = {}
        self.commands = []

    def sample(self, rec, host_unix):
        self.frames += 1
        if self.first_seq is None:
            self.first_seq = rec["seq"]
            self.first_ts = rec["ts_us"]
            self.first_host = host_unix
        else:
            expected = (self.last_seq + 1) & 0xFFFFFFFF
            delta = (rec["seq"] - expected) & 0xFFFFFFFF
            if delta:
                self.gap_events += 1
                self.missing += delta
        self.last_seq = rec["seq"]
        self.last_ts = rec["ts_us"]
        self.last_host = host_unix
        if not rec["flags"] & FLAG_TIME_VALID:
            self.invalid_time += 1
        if rec["flags"] & FLAG_DROPPED_BEFORE:
            self.dropped_flag += 1
        self.flags[rec["flags"]] = self.flags.get(rec["flags"], 0) + 1

    def summary(self):
        elapsed = (self.last_host - self.first_host) if self.first_host else 0.0
        span = ((self.last_seq - self.first_seq) & 0xFFFFFFFF) if self.first_seq is not None else 0
        ts_span = ((self.last_ts - self.first_ts) / 1e6) if self.first_ts is not None else 0.0
        out = {
            "frames": self.frames,
            "gap_events": self.gap_events,
            "missing_samples": self.missing,
            "gap_fraction": (self.missing / (span + 1)) if span else None,
            "crc_errors": self.crc_errors,
            "resyncs": self.resyncs,
            "frames_flag_dropped_before": self.dropped_flag,
            "frames_time_invalid": self.invalid_time,
            "first_sequence": self.first_seq,
            "last_sequence": self.last_seq,
            "sequence_span": span,
            "host_duration_s": elapsed,
            "host_frame_rate_sps": (self.frames / elapsed) if elapsed > 0 else None,
            "timestamp_span_s": ts_span,
            "device_rate_sps": (span / ts_span) if ts_span > 0 else None,
            "flag_histogram": {str(k): v for k, v in sorted(self.flags.items())},
        }
        return out


class FrameReader:
    def __init__(self, sock, stats):
        self.sock = sock
        self.stats = stats
        self.buf = bytearray()

    def read_frame(self, timeout):
        deadline = time.time() + timeout
        while True:
            frame = self._parse()
            if frame is not None:
                return frame
            remaining = deadline - time.time()
            if remaining <= 0:
                return None
            self.sock.settimeout(min(0.5, remaining))
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise ConnectionError("device closed the TCP connection")
            self.buf.extend(data)

    def _parse(self):
        while True:
            idx = self.buf.find(SYNC)
            if idx < 0:
                if self.buf and self.buf[-1] == 0xA5:
                    del self.buf[:-1]
                else:
                    self.buf.clear()
                return None
            if idx:
                del self.buf[:idx]
                self.stats.resyncs += 1
            if len(self.buf) < 4:
                return None
            if self.buf[2] != PROTOCOL_VERSION:
                del self.buf[0]
                self.stats.resyncs += 1
                continue
            typ = self.buf[3]
            if typ == T_SAMPLE:
                if len(self.buf) < SAMPLE_HEADER:
                    return None
                plen = sample_payload_len(self.buf)
                if plen not in (27, 54, 81, 108):
                    del self.buf[0]
                    self.stats.resyncs += 1
                    continue
                total = 28 + plen
            elif typ in (T_INFO, T_STATUS, T_ACK, T_EVENT):
                if len(self.buf) < 12:
                    return None
                total = 14 + u16(self.buf, 10)
            else:
                del self.buf[0]
                self.stats.resyncs += 1
                continue
            if len(self.buf) < total:
                return None
            if crc16_ccitt_false(self.buf[2:total - 2]) != u16(self.buf, total - 2):
                self.stats.crc_errors += 1
                del self.buf[0]
                continue
            frame = bytes(self.buf[:total])
            del self.buf[:total]
            return frame


def http_json(url, method, payload=None, timeout=5.0):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def local_ip_toward(host):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((host, 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--port", type=int, default=12345, help="local TCP listener port")
    ap.add_argument("--http-host", default="192.168.4.1", help="device AP IP")
    ap.add_argument("--advertise-ip", default=None,
                    help="host IP the device should connect to (default: auto)")
    ap.add_argument("--profile", default="short", choices=sorted(PROFILES))
    ap.add_argument("--rate", type=int, default=250, choices=[250, 500])
    ap.add_argument("--boards", type=int, default=1, choices=[1, 2, 3, 4])
    ap.add_argument("--channels", type=lambda s: int(s, 0), default=0xFF)
    ap.add_argument("--duration", type=float, default=0.0,
                    help="seconds; 0 = until Ctrl+C")
    ap.add_argument("--no-delete", action="store_true",
                    help="do not DELETE /tcp on exit")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    raw_path = os.path.join(args.outdir, "raw_frames.bin")
    csv_path = os.path.join(args.outdir, "samples.csv")
    meta_path = os.path.join(args.outdir, "meta.json")

    stats = Stats()
    device_info = None
    device_status = None
    error = None
    conn = None
    listener = None
    advertise = args.advertise_ip or local_ip_toward(args.http_host)
    started_at = utc_now()

    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", args.port))
        listener.listen(1)
        listener.settimeout(30)
        print("listening on 0.0.0.0:%d; advertising %s" % (args.port, advertise),
              flush=True)
        if not advertise.startswith("192.168.4."):
            print("WARNING: %s is not on the board AP subnet; join OpenBCI-XXXX "
                  "first or pass --advertise-ip" % advertise, flush=True)

        status, body = http_json(
            "http://%s/tcp" % args.http_host, "POST",
            {"ip": advertise, "port": args.port, "output": "bcikit",
             "latency": 10000})
        print("POST /tcp -> %d %s" % (status, body), flush=True)

        conn, peer = listener.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print("device connected from %s:%d" % peer, flush=True)
        reader = FrameReader(conn, stats)
        next_rid = [1]

        def send(cmd, payload=b"", expect_ack=True, timeout=3.0):
            rid = next_rid[0]
            next_rid[0] += 1
            conn.sendall(command_frame(rid, cmd, payload))
            deadline = time.time() + timeout
            while time.time() < deadline:
                frame = reader.read_frame(deadline - time.time())
                if frame is None:
                    break
                typ = frame[3]
                if u32(frame, 4) != rid:
                    continue
                if typ == T_ACK:
                    code, ack_status = frame[8], frame[9]
                    stats.commands.append({"request_id": rid, "command": code,
                                           "status": ack_status})
                    if ack_status != 0:
                        raise RuntimeError("command 0x%02X failed: status %d"
                                           % (code, ack_status))
                    return frame
                if typ == T_INFO:
                    info = decode_info(frame)
                    stats.commands.append({"request_id": rid, "command": CMD_GET_INFO,
                                           "status": 0, "info": info})
                    return frame
                if typ == T_STATUS:
                    status = decode_status(frame)
                    stats.commands.append({"request_id": rid, "command": CMD_GET_STATUS,
                                           "status": 0, "status": status})
                    return frame
                if typ == T_EVENT:
                    stats.commands.append({"request_id": rid, "event": frame.hex()})
            raise TimeoutError("no reply to command 0x%02X" % cmd)

        send(CMD_STOP)
        send(CMD_SET_OUTPUT, bytes([0]))
        send(CMD_SET_BOARDS, bytes([args.boards]))
        send(CMD_SET_RATE, struct.pack("<H", args.rate))
        send(CMD_SET_PROFILE, bytes([PROFILES[args.profile]]))
        send(CMD_SET_MASK, bytes([args.channels & 0xFF]))
        info_frame = send(CMD_GET_INFO)
        device_info = decode_info(info_frame)
        status_frame = send(CMD_GET_STATUS)
        device_status = decode_status(status_frame)
        send(CMD_START)
        print("started: %s, boards=%d, rate=%d, profile=%s" % (
            device_info["firmware"], args.boards, args.rate, args.profile),
            flush=True)

        window_start = time.time()
        rows_since_flush = 0
        deadline = (time.time() + args.duration) if args.duration > 0 else None

        with open(raw_path, "wb") as raw_fh, open(csv_path, "w", newline="") as csv_fh:
            writer = csv.writer(csv_fh)
            header = ["host_unix", "seq", "timestamp_us", "flags", "sample_rate_hz",
                      "gain_code", "status"] + [
                "ch%02d" % (i + 1) for i in range(args.boards * 8)]
            writer.writerow(header)
            while True:
                if deadline is not None and time.time() >= deadline:
                    break
                frame = reader.read_frame(0.5)
                if frame is None:
                    continue
                typ = frame[3]
                if typ != T_SAMPLE:
                    continue
                host_unix = time.time()
                rec = decode_sample(frame)
                if not rec["channels"]:
                    continue
                stats.sample(rec, host_unix)
                raw_fh.write(frame)
                writer.writerow([("%.6f" % host_unix), rec["seq"], rec["ts_us"],
                                 "0x%04X" % rec["flags"], rec["rate"], rec["gain"],
                                 "+".join(rec["status"])] + rec["channels"])
                rows_since_flush += 1
                if rows_since_flush >= 1000:
                    csv_fh.flush()
                    rows_since_flush = 0
                if time.time() - window_start >= 10.0:
                    summ = stats.summary()
                    print("t=%6.1fs frames=%d host=%.1f sps dev=%s gaps=%d(%.3f%%) crc=%d"
                          % (time.time() - window_start, summ["frames"],
                             summ["host_frame_rate_sps"] or 0,
                             ("%.1f" % summ["device_rate_sps"]) if summ["device_rate_sps"] else "n/a",
                             summ["gap_events"],
                             100.0 * (summ["gap_fraction"] or 0),
                             summ["crc_errors"]), flush=True)
                    window_start = time.time()

        try:
            conn.sendall(command_frame(next_rid[0], CMD_STOP))
            next_rid[0] += 1
            end = time.time() + 1.0
            while time.time() < end:
                frame = reader.read_frame(end - time.time())
                if frame is None:
                    break
                if frame[3] == T_ACK:
                    stats.commands.append({"request_id": u32(frame, 4),
                                           "command": frame[8], "status": frame[9],
                                           "note": "final stop"})
                    break
        except Exception:
            pass
    except KeyboardInterrupt:
        print("interrupted", flush=True)
    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        print("ERROR:", error, flush=True)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass
        if not args.no_delete:
            try:
                http_json("http://%s/tcp" % args.http_host, "DELETE")
            except Exception:
                pass

        summary = stats.summary()
        meta = {
            "label": os.path.basename(os.path.abspath(args.outdir)),
            "protocol": "BCIKit Raw Stream v1 over WiFi TCP",
            "started_at_utc": started_at,
            "ended_at_utc": utc_now(),
            "advertise_ip": advertise,
            "http_host": args.http_host,
            "listen_port": args.port,
            "requested": {"boards": args.boards, "rate": args.rate,
                          "profile": args.profile, "channels": args.channels,
                          "duration_s": args.duration},
            "device_info": device_info,
            "device_status": device_status,
            "commands": stats.commands,
            "statistics": summary,
            "host": platform.node(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "scale": {"gain_code": 6, "gain": 24, "vref_v": 4.5,
                      "lsb_mv": LSB_MV, "full_scale_mv": 187.5},
            "files": {"raw_frames.bin": "exact SAMPLE wire frames",
                      "samples.csv": "decoded rows; host_unix is arrival time",
                      "meta.json": "this file"},
            "notes": [
                "timestamp_us is the device DRDY time, valid when flag TIME_VALID is set.",
                "sequence is 32-bit and continues across transport drops.",
                "raw_frames.bin is the audit source; samples.csv is derived.",
                "The board AP has no internet; the host is offline while connected.",
            ],
            "error": error,
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        sums = []
        for name in ("raw_frames.bin", "samples.csv", "meta.json"):
            path = os.path.join(args.outdir, name)
            if os.path.exists(path):
                sums.append("%s  %s" % (sha256_file(path), name))
        with open(os.path.join(args.outdir, "SHA256SUMS"), "w") as fh:
            fh.write("\n".join(sums) + "\n")
        print("wrote %s" % args.outdir, flush=True)
    return 0 if error is None else 1


if __name__ == "__main__":
    sys.exit(main())
