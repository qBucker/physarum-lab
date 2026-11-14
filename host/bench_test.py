#!/usr/bin/env python3
"""台架数据分析：噪声、漂移、50 Hz、PSD。

支持两种 CSV：

- BCIKit / ADS1299（samples.csv）：host_time_iso,host_unix,sample_number,ch1..ch8
  单位 counts；counts → mV 用 --lsb-nv（默认 22.3517 nV/count，gain 24、VREF 4.5 V）。
  时基用 sample_number 重建的序号 / --fs（默认 250），不用主机时间戳。
- ADS1256 legacy（raw.csv）：host_unix,mV,marker。

用法：
    python3 bench_test.py data/bench_T1/samples.csv --label T1
    python3 bench_test.py data/bench_T1/samples.csv --label T1 --channel 2
    python3 bench_test.py data/sim_001/raw.csv --label sim --max-noise-uv 50
    python3 bench_test.py data/bench_T4/samples.csv --label T4 \
        --max-noise-uv 1000 --max-drift-mv-h 1000 --max-mains-ratio 0.5

输出（与 CSV 同目录）：
    bench_summary.json
    bench_plot.png

判据（可在命令行覆盖）：
    --max-noise-uv 5         0.01–min(5, fs/2) Hz 频带 RMS 上限（µV）
    --max-drift-mv-h 1.0     漂移上限（mV/h）
    --max-mains-ratio 0.5    49–51 Hz 功率 / 45–55 Hz 功率 上限
                             （仅当 fs > 100 时适用）

说明：
- BCIKit 250 SPS：Nyquist 125 Hz，50 Hz 在带内，T4 可直接判。
- 用 --channel 选择主通道（默认 1）；pass 以主通道为准，
  同时输出 channels_pass_all 供一致性检查。
- 本脚本面向台架（≤1 h）；48 h 记录不在此处整表加载。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import numpy as np
from scipy import signal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BCIKIT_LSB_NV = 22.3517  # VREF 4.5 V, gain 24: 4.5 / (24 * 2^23) V


def read_csv(path: str, fs: float, lsb_nv: float):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        if "sample_number" in fields and "ch1" in fields:
            return read_bcikit(reader, path, fs, lsb_nv)
        return read_legacy(reader, path)


def read_legacy(reader, path: str):
    t, mv, marker = [], [], []
    for row in reader:
        if not row or row.get("mV") in (None, ""):
            continue
        try:
            t.append(float(row["host_unix"]))
            mv.append(float(row["mV"]))
            marker.append(int(float(row.get("marker", 0) or 0)))
        except (ValueError, KeyError):
            continue
    if len(t) < 10:
        raise SystemExit(f"not enough samples in {path}: {len(t)}")
    t = np.asarray(t, dtype=float)
    mv = np.asarray(mv, dtype=float)
    marker = np.asarray(marker, dtype=int)
    order = np.argsort(t)
    return {
        "format": "ads1256",
        "t_host": t[order],
        "t_analysis": t[order],
        "channels_mv": mv[order, None],
        "channel_names": ["mV"],
        "marker": marker[order],
        "sequence": None,
    }


def read_bcikit(reader, path: str, fs: float, lsb_nv: float):
    t_host, sample_no, rows = [], [], []
    for row in reader:
        if not row or row.get("ch1") in (None, ""):
            continue
        try:
            t_host.append(float(row["host_unix"]))
            sample_no.append(int(float(row["sample_number"])))
            rows.append([float(row[f"ch{i}"]) for i in range(1, 9)])
        except (ValueError, KeyError):
            continue
    if len(t_host) < 10:
        raise SystemExit(f"not enough samples in {path}: {len(t_host)}")

    t_host = np.asarray(t_host, dtype=float)
    sample_no = np.asarray(sample_no, dtype=np.int64)
    counts = np.asarray(rows, dtype=float)

    # Rebuild a continuous sequence from the 1-byte sample_number.
    seq = np.zeros(len(sample_no), dtype=np.int64)
    gaps = 0
    gap_samples = 0
    zero_steps = 0
    for i in range(1, len(sample_no)):
        step = int((sample_no[i] - sample_no[i - 1]) % 256)
        if step == 0:
            zero_steps += 1  # duplicate, or a 256-sample gap (ambiguous)
        elif step > 1:
            gaps += 1
            gap_samples += step - 1
        seq[i] = seq[i - 1] + step

    duration_host = float(t_host[-1] - t_host[0])
    # seq_span already counts every produced sample interval, including the
    # missing ones (each step adds its full size to the cumulative sequence).
    seq_span = int(seq[-1] - seq[0])
    fs_effective = (seq_span / duration_host
                    if duration_host > 0 and seq_span > 0 else fs)
    return {
        "format": "bcikit",
        "t_host": t_host,
        # Use the measured sample clock (not the nominal rate) so that
        # frequencies are absolute: the BCIKit sample clock is 242–247 SPS
        # in practice, not exactly 250.
        "t_analysis": seq.astype(float) / fs_effective,
        "channels_mv": counts * (lsb_nv / 1e6),  # nV -> mV
        "channel_names": [f"ch{i}" for i in range(1, 9)],
        "marker": np.zeros(len(t_host), dtype=int),
        "sequence": {
            "samples": int(len(seq)),
            "span_samples": seq_span,
            "gaps": int(gaps),
            "gap_samples": int(gap_samples),
            "zero_steps": int(zero_steps),
            "gap_fraction": float(gap_samples / seq_span) if seq_span > 0 else float("nan"),
            "fs_nominal_hz": float(fs),
            "fs_effective_hz": float(fs_effective),
            "effective_sps_sample_clock": float(fs_effective),
            "effective_sps_host_clock": float(len(seq) / duration_host)
            if duration_host > 0 else float("nan"),
        },
    }


def analyze(t, mv, marker, args):
    dt = np.diff(t)
    dt = dt[(dt > 0) & np.isfinite(dt)]
    fs = 1.0 / np.median(dt) if len(dt) else 10.0
    n = len(mv)
    duration = t[-1] - t[0]

    mean_mv = float(np.mean(mv))
    std_mv = float(np.std(mv, ddof=1))
    ptp_mv = float(np.ptp(mv))

    # 去趋势（线性）
    x = np.arange(n) / fs
    coef = np.polyfit(x, mv, 1)
    trend = np.polyval(coef, x)
    detrended = mv - trend
    noise_uv = float(np.std(detrended, ddof=1) * 1000.0)
    drift_mv_h = float(coef[0] * 3600.0)

    # 50 Hz notch（分析层；采集端不过滤，保留原始数据）
    if args.notch > 0 and fs > 2.0 * args.notch and len(detrended) > 16:
        b, a = signal.iirnotch(args.notch, args.notch_q, fs)
        notched = signal.filtfilt(b, a, detrended)
    else:
        notched = detrended

    # PSD：raw 与 notched 各一份
    nperseg = int(min(4096, max(256, n // 4)))
    f, psd_raw = signal.welch(detrended, fs=fs, nperseg=nperseg, detrend="linear")
    _, psd = signal.welch(notched, fs=fs, nperseg=nperseg, detrend="linear")
    df = f[1] - f[0] if len(f) > 1 else 1.0

    def band_rms_uv(lo, hi):
        m = (f >= lo) & (f <= hi)
        if not np.any(m):
            return float("nan")
        return float(np.sqrt(np.sum(psd[m]) * df) * 1000.0)

    noise_band_lo = args.band_lo
    noise_band_hi = min(args.band_hi, fs / 2.0)
    noise_band_uv = band_rms_uv(noise_band_lo, noise_band_hi)

    mains_applicable = args.notch > 0 and fs > 2.0 * args.notch
    mains_band = (f >= 45.0) & (f <= 55.0)
    mains_peak = (f >= 49.0) & (f <= 51.0)

    def mains_ratio_of(p):
        return float(
            np.sum(p[mains_peak]) / np.sum(p[mains_band])
            if np.any(mains_band) and np.sum(p[mains_band]) > 0 else float("nan")
        )

    mains_ratio_raw = mains_ratio_of(psd_raw) if mains_applicable else float("nan")
    mains_ratio = mains_ratio_of(psd) if mains_applicable else float("nan")

    # 分箱均值漂移（10 s）
    bin_s = 10.0
    bins = np.floor((t - t[0]) / bin_s).astype(int)
    bx, by = [], []
    for b in np.unique(bins):
        m = bins == b
        if np.sum(m) >= 3:
            bx.append(float(np.mean(t[m] - t[0])))
            by.append(float(np.mean(mv[m])))
    if len(bx) >= 3:
        slope_bin = np.polyfit(bx, by, 1)[0]
        drift_bin_mv_h = float(slope_bin * 3600.0)
    else:
        drift_bin_mv_h = float("nan")

    # 标记
    marker_count = int(np.sum(np.diff(np.r_[0, marker]) == 1)) if n else 0

    summary = {
        "n": int(n),
        "duration_s": float(duration),
        "fs_median_hz": float(fs),
        "mean_mV": mean_mv,
        "std_mV": std_mv,
        "ptp_mV": ptp_mv,
        "noise_uv_detrended": noise_uv,
        "noise_band_uv": noise_band_uv,
        "noise_band_lo_hz": noise_band_lo,
        "noise_band_hi_hz": noise_band_hi,
        "drift_mV_per_h_linear": drift_mv_h,
        "drift_mV_per_h_binned": drift_bin_mv_h,
        "notch_hz": args.notch,
        "mains_applicable": bool(mains_applicable),
        "mains_49_51_over_45_55_raw": mains_ratio_raw,
        "mains_49_51_over_45_55": mains_ratio,
        "marker_count": marker_count,
    }

    mains_ok = True if not mains_applicable else bool(
        np.isfinite(mains_ratio) and mains_ratio <= args.max_mains_ratio
    )
    checks = {
        "noise_band": bool(np.isfinite(noise_band_uv) and noise_band_uv <= args.max_noise_uv),
        "drift": bool(np.isfinite(drift_bin_mv_h) and abs(drift_bin_mv_h) <= args.max_drift_mv_h),
        "mains": mains_ok,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())
    summary["thresholds"] = {
        "max_noise_uv": args.max_noise_uv,
        "max_drift_mv_h": args.max_drift_mv_h,
        "max_mains_ratio": args.max_mains_ratio,
    }
    return summary, f, psd, detrended


def plot(t, mv, f, psd, summary, outpath):
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)

    # 时间序列：最多画前 120 s
    m = (t - t[0]) <= min(120.0, t[-1] - t[0])
    ax[0].plot(t[m] - t[0], mv[m], lw=0.8, color="#1f4e79")
    ax[0].set_xlabel("time (s)")
    ax[0].set_ylabel("voltage (mV)")
    ax[0].set_title(f"time series (first {min(120, t[-1] - t[0]):.0f} s)")
    ax[0].grid(alpha=0.2)

    # PSD
    ax[1].loglog(f[1:], psd[1:], lw=0.9, color="#b45309")
    if summary["mains_applicable"]:
        ax[1].axvline(50.0, color="gray", ls="--", lw=0.7)
        mains_text = "mains raw/notch %.2f/%.2f" % (
            summary["mains_49_51_over_45_55_raw"],
            summary["mains_49_51_over_45_55"],
        )
    else:
        mains_text = "mains n/a (fs=%.0f SPS < 100)" % summary["fs_median_hz"]
    ax[1].set_xlabel("frequency (Hz)")
    ax[1].set_ylabel("PSD (mV²/Hz)")
    ax[1].set_title(
        "PSD | noise %.1f µV (%.3g–%.3g Hz) | drift %.2f mV/h | %s"
        % (
            summary["noise_band_uv"],
            summary["noise_band_lo_hz"],
            summary["noise_band_hi_hz"],
            summary["drift_mV_per_h_binned"],
            mains_text,
        )
    )
    ax[1].grid(alpha=0.2, which="both")

    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--label", default="")
    p.add_argument("--channel", type=int, default=1,
                   help="1-based channel for plot/pass (BCIKit; default 1)")
    p.add_argument("--fs", type=float, default=250.0,
                   help="nominal sample rate for the BCIKit sample clock")
    p.add_argument("--lsb-nv", type=float, default=BCIKIT_LSB_NV,
                   help="BCIKit LSB in nV/count (gain 24, VREF 4.5 V)")
    p.add_argument("--band-lo", type=float, default=0.01)
    p.add_argument("--band-hi", type=float, default=5.0)
    p.add_argument("--max-noise-uv", type=float, default=5.0)
    p.add_argument("--max-drift-mv-h", type=float, default=1.0)
    p.add_argument("--max-mains-ratio", type=float, default=0.5)
    p.add_argument("--notch", type=float, default=50.0,
                   help="mains notch frequency; 0 disables")
    p.add_argument("--notch-q", type=float, default=30.0)
    args = p.parse_args()

    data = read_csv(args.csv, args.fs, args.lsb_nv)
    channels = data["channels_mv"]
    n_ch = channels.shape[1]
    idx = args.channel - 1
    if not (0 <= idx < n_ch):
        raise SystemExit(f"--channel out of range: 1..{n_ch}")

    results = []
    for j, name in enumerate(data["channel_names"]):
        summ, f, psd, detrended = analyze(
            data["t_analysis"], channels[:, j], data["marker"], args
        )
        results.append({
            "name": name,
            "summary": summ,
            "f": f,
            "psd": psd,
            "detrended": detrended,
        })

    chosen = results[idx]
    summary = chosen["summary"]
    summary["label"] = args.label
    summary["csv"] = os.path.abspath(args.csv)
    summary["format"] = data["format"]
    summary["channel"] = chosen["name"]
    summary["channels"] = {
        r["name"]: {
            "noise_band_uv": r["summary"]["noise_band_uv"],
            "drift_mV_per_h_binned": r["summary"]["drift_mV_per_h_binned"],
            "pass": r["summary"]["pass"],
        }
        for r in results
    }
    summary["channels_pass_all"] = all(r["summary"]["pass"] for r in results)
    summary["sequence"] = data["sequence"]
    summary["pass"] = chosen["summary"]["pass"]

    outdir = os.path.dirname(os.path.abspath(args.csv))
    with open(os.path.join(outdir, "bench_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    plot(data["t_analysis"], channels[:, idx], chosen["f"], chosen["psd"],
         summary, os.path.join(outdir, "bench_plot.png"))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nRESULT:", "PASS" if summary["pass"] else "FAIL")
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
