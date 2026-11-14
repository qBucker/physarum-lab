#!/usr/bin/env python3
"""ADS1256 串口记录器（ESP32 → 笔记本）。

用法：
    # 无硬件：生成已知信号，验证管线
    python3 log_serial.py --simulate --duration 120 --outdir data/sim_001

    # 真实采集（10 SPS，50/60 Hz 抑制）
    python3 log_serial.py --port /dev/ttyUSB0 --pga 3 --drate 10 --duration 300 --outdir data/bench_T1

    # T4：50 Hz 检查（1 kSPS 单独跑）
    python3 log_serial.py --port /dev/ttyUSB0 --pga 3 --drate 1000 --duration 60 --outdir data/bench_T4

输出：
    <outdir>/raw.csv        host_time_iso,host_unix,arduino_micros,mode,raw,mV,marker
    <outdir>/meta.json      采集参数与统计
    <outdir>/SHA256SUMS     raw.csv 的 sha256

设计原则：
- 原始数据只追加，不覆盖；
- 每 20 行 flush，每 1000 行 fsync；
- Ctrl-C 正常收尾并写 meta/SHA256。
- 固件侧的 buffer ON、差分 MUX、2.5 V 基准、10 SPS 由 ads1256_logger.ino 设置。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import signal
import sys
import time

import numpy as np

# PGA index 0..6 -> gain 1,2,4,8,16,32,64
PGA_GAIN = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64}
VREF_MV = 2500.0  # REF3025 2.5 V


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_meta(outdir: str, meta: dict) -> None:
    with open(os.path.join(outdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def write_sums(outdir: str, filename: str) -> str:
    digest = sha256_file(os.path.join(outdir, filename))
    with open(os.path.join(outdir, "SHA256SUMS"), "w", encoding="utf-8") as f:
        f.write(f"{digest}  {filename}\n")
    return digest


def full_scale_mv(pga_index: int) -> float:
    return VREF_MV / PGA_GAIN[pga_index]


def simulate(args) -> dict:
    """生成已知慢信号 + 噪声，用于无硬件验证。

    10 SPS 时 50 Hz 超过 Nyquist，不会加入；T4 请用 --drate 1000。
    """
    fs_hz = float(args.drate)
    n = int(args.duration * fs_hz)
    t = np.arange(n) / fs_hz
    rng = np.random.default_rng(args.seed)

    sig = (
        args.sim_slow_mv * np.sin(2 * math.pi * 0.05 * t)
        + args.sim_mid_mv * np.sin(2 * math.pi * 0.30 * t)
        + rng.normal(0.0, args.sim_noise_uv / 1000.0, n)
    )
    mains_added = 0.0
    if args.sim_mains_mv > 0:
        if fs_hz > 100.0:
            sig = sig + args.sim_mains_mv * np.sin(2 * math.pi * 50.0 * t)
            mains_added = args.sim_mains_mv
        else:
            print(
                f"[sim] warning: 50 Hz is above Nyquist at {fs_hz:g} SPS; "
                "mains component not added (use --drate 1000 for T4)."
            )

    fs_mv = full_scale_mv(args.pga)
    raw = np.clip(np.round(sig / fs_mv * (2 ** 23)), -(2 ** 23), 2 ** 23 - 1).astype(int)
    mv = raw * fs_mv / (2 ** 23)
    marker = ((t % 30.0) < 0.5).astype(int)

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "raw.csv")
    start_unix = time.time()
    start_iso = iso_now()

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["host_time_iso", "host_unix", "arduino_micros", "mode", "raw", "mV", "marker"])
        for i in range(n):
            ts = start_unix + i / fs_hz
            w.writerow([
                dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="milliseconds"),
                f"{ts:.6f}",
                int(round(i / fs_hz * 1_000_000)),
                "diff01" if args.mode == "diff" else "single0",
                int(raw[i]),
                f"{mv[i]:.6f}",
                int(marker[i]),
            ])
            if i % 20 == 0:
                f.flush()

    digest = write_sums(outdir, "raw.csv")
    meta = {
        "run_id": os.path.basename(os.path.abspath(outdir)),
        "label": args.label,
        "note": args.note,
        "simulate": True,
        "adc": "ADS1256",
        "start_iso": start_iso,
        "end_iso": iso_now(),
        "duration_s": args.duration,
        "samples": n,
        "sample_rate_sps": fs_hz,
        "pga_index": args.pga,
        "pga_gain": PGA_GAIN[args.pga],
        "vref_mV": VREF_MV,
        "full_scale_mV": fs_mv,
        "mode": "diff01" if args.mode == "diff" else "single0",
        "sim": {
            "slow_mv": args.sim_slow_mv,
            "mid_mv": args.sim_mid_mv,
            "mains_mv": mains_added,
            "noise_uv": args.sim_noise_uv,
            "seed": args.seed,
            "drate": args.drate,
            "pga": args.pga,
        },
        "host": platform.node(),
        "python": sys.version.split()[0],
        "output": "raw.csv",
        "sha256": digest,
    }
    write_meta(outdir, meta)
    print(f"[sim] {n} samples -> {path}")
    print(f"[sim] sha256 {digest}")
    return meta


def run_serial(args) -> dict:
    import serial  # 延迟导入，simulate 模式不需要串口

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "raw.csv")
    start_unix = time.time()
    start_iso = iso_now()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=2.0)
    except Exception as e:
        print(f"[error] 无法打开串口 {args.port}: {e}", file=sys.stderr)
        print("提示：WSL 下需先用 usbipd attach；Windows 下端口形如 COM3。", file=sys.stderr)
        raise SystemExit(2)

    time.sleep(0.3)
    ser.reset_input_buffer()
    # 配置：暂停 → PGA → 差分/单端 → 数据率 → 开始
    ser.write(b"p")
    time.sleep(0.1)
    ser.write(f"g{args.pga}".encode())
    time.sleep(0.1)
    ser.write(b"d" if args.mode == "diff" else b"u")
    time.sleep(0.1)
    ser.write(b"t0" if args.drate == 10 else b"t1")
    time.sleep(0.2)
    ser.write(b"s")

    samples = 0
    stop = {"flag": False}

    def handle_sigint(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_sigint)

    last_print = time.time()

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["host_time_iso", "host_unix", "arduino_micros", "mode", "raw", "mV", "marker"])
        while not stop["flag"]:
            if args.duration > 0 and (time.time() - start_unix) >= args.duration:
                break
            try:
                line = ser.readline().decode("utf-8", errors="replace").strip()
            except Exception as e:
                print(f"[warn] 串口读取失败: {e}", file=sys.stderr)
                time.sleep(0.5)
                continue
            if not line:
                continue
            if line.startswith("#"):
                print(f"[esp32] {line}")
                continue
            parts = line.split(",")
            if len(parts) != 5:
                continue
            try:
                micros = int(parts[0])
                mode = parts[1]
                raw = int(parts[2])
                mv = float(parts[3])
                marker = int(parts[4])
            except ValueError:
                continue

            now = time.time()
            w.writerow([
                iso_now(),
                f"{now:.6f}",
                micros,
                mode,
                raw,
                f"{mv:.6f}",
                marker,
            ])
            samples += 1
            if samples % 20 == 0:
                f.flush()
            if samples % 1000 == 0:
                f.flush()
                os.fsync(f.fileno())

            if now - last_print >= 5.0:
                print(f"[run] {samples} samples, {samples / max(now - start_unix, 1e-9):.1f} SPS")
                last_print = now

    # 停止
    try:
        ser.write(b"p")
    except Exception:
        pass
    ser.close()

    digest = write_sums(outdir, "raw.csv")
    meta = {
        "run_id": os.path.basename(os.path.abspath(outdir)),
        "label": args.label,
        "note": args.note,
        "simulate": False,
        "adc": "ADS1256",
        "port": args.port,
        "baud": args.baud,
        "start_iso": start_iso,
        "end_iso": iso_now(),
        "duration_s": time.time() - start_unix,
        "samples": samples,
        "sample_rate_sps": args.drate,
        "pga_index": args.pga,
        "pga_gain": PGA_GAIN[args.pga],
        "vref_mV": VREF_MV,
        "full_scale_mV": full_scale_mv(args.pga),
        "mode": "diff01" if args.mode == "diff" else "single0",
        "host": platform.node(),
        "python": sys.version.split()[0],
        "output": "raw.csv",
        "sha256": digest,
    }
    write_meta(outdir, meta)
    print(f"[done] {samples} samples -> {path}")
    print(f"[done] sha256 {digest}")
    return meta


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ADS1256 serial logger for Physarum phase 0")
    p.add_argument("--port", default="/dev/ttyUSB0", help="serial port (COM3 on Windows)")
    p.add_argument("--baud", type=int, default=921600,
                   help="ESP32 USB serial baud; 921600 needed for 1 kSPS T4")
    p.add_argument("--pga", type=int, default=3, choices=range(0, 7),
                   help="PGA index 0..6 => gain 1,2,4,8,16,32,64; default 3 (PGA=8, ±312.5 mV)")
    p.add_argument("--drate", type=int, default=10, choices=[10, 1000],
                   help="ADS1256 data rate: 10 (50/60 Hz rejection) or 1000 (T4 mains test)")
    p.add_argument("--mode", choices=["diff", "single"], default="diff")
    p.add_argument("--duration", type=float, default=0.0,
                   help="seconds; 0 = until Ctrl-C")
    p.add_argument("--outdir", default="data/run")
    p.add_argument("--label", default="")
    p.add_argument("--note", default="")
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--seed", type=int, default=20261107)
    p.add_argument("--sim-slow-mv", type=float, default=2.0)
    p.add_argument("--sim-mid-mv", type=float, default=0.5)
    p.add_argument("--sim-mains-mv", type=float, default=0.0,
                   help="50 Hz amplitude; only added when --drate 1000 (T4)")
    p.add_argument("--sim-noise-uv", type=float, default=20.0)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.duration <= 0 and not args.simulate:
        print("[info] duration=0 → 采集直到 Ctrl-C")
    if args.simulate:
        simulate(args)
    else:
        run_serial(args)


if __name__ == "__main__":
    main()
