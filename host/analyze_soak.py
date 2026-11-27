#!/usr/bin/env python3
"""Streaming gap/stall audit for a BCIkit OpenBCI CSV soak.

Reads `samples.csv` once, without retaining samples.  The 8-bit OpenBCI
sample number is used to reconstruct missing-sample gaps; host timestamps
are used only for batch/stall statistics and per-hour binning.

Usage:
    python3 -I analyze_soak.py samples.csv [--meta meta.json] > analysis.json
"""
import argparse
import csv
import heapq
import json
from collections import Counter


def _status_counters(text):
    """Extract numeric key=value counters from a firmware status block."""
    out = {}
    if not text:
        return out
    for line in text.splitlines():
        for token in line.replace("\n", " ").split():
            if "=" not in token:
                continue
            key, val = token.split("=", 1)
            if key in {
                "drdy", "frames", "sync_error", "spi_error", "timeout",
                "queue_overrun", "transport_drop", "verify_error",
            }:
                try:
                    out[key] = int(val)
                except ValueError:
                    pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--meta", default=None)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    first_iso = last_iso = None
    first_ts = last_ts = prev_ts = None
    prev_sample = None
    rows = 0

    unique_ts = 0
    batch_size = 0
    batch_hist = Counter()

    gap_count = 0
    gap_top = []  # min-heap of (gap, before, after)
    gap_gt = {0.05: 0, 0.1: 0, 0.5: 0, 1.0: 0, 5.0: 0}
    gap_max = 0.0

    normal_steps = 0
    seq_gap_events = 0
    missing_total = 0
    duplicates = 0
    max_step = 0
    missing_hist = Counter()

    hour_received = Counter()
    hour_missing = Counter()
    hour_gap_events = Counter()

    with open(args.csv_path, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        for row in reader:
            rows += 1
            ts = float(row[1])
            sample = int(row[2])
            iso = row[0]

            if first_ts is None:
                first_ts = ts
                first_iso = iso
            if prev_ts is None:
                prev_ts = ts
                batch_size = 1
            elif ts == prev_ts:
                batch_size += 1
            else:
                batch_hist[batch_size] += 1
                unique_ts += 1
                gap = ts - prev_ts
                gap_count += 1
                gap_max = max(gap_max, gap)
                for threshold in gap_gt:
                    if gap > threshold:
                        gap_gt[threshold] += 1
                item = (gap, prev_ts, ts)
                if len(gap_top) < args.top:
                    heapq.heappush(gap_top, item)
                elif gap > gap_top[0][0]:
                    heapq.heapreplace(gap_top, item)
                prev_ts = ts
                batch_size = 1

            hour = int((ts - first_ts) // 3600)
            hour_received[hour] += 1

            if prev_sample is not None:
                step = (sample - prev_sample) % 256
                max_step = max(max_step, step)
                if step == 1:
                    normal_steps += 1
                elif step == 0:
                    duplicates += 1
                else:
                    missing = step - 1
                    seq_gap_events += 1
                    missing_total += missing
                    missing_hist[missing] += 1
                    hour_missing[hour] += missing
                    hour_gap_events[hour] += 1
            prev_sample = sample
            last_ts = ts
            last_iso = iso

    if batch_size:
        batch_hist[batch_size] += 1
        unique_ts += 1

    hours = sorted(set(hour_received) | set(hour_missing))
    per_hour = []
    for h in hours:
        rec = hour_received.get(h, 0)
        miss = hour_missing.get(h, 0)
        denom = rec + miss
        per_hour.append({
            "hour": h,
            "received": rec,
            "missing": miss,
            "gap_events": hour_gap_events.get(h, 0),
            "gap_fraction_pct": (100.0 * miss / denom) if denom else 0.0,
        })

    out = {
        "csv": args.csv_path,
        "rows": rows,
        "first_iso": first_iso,
        "last_iso": last_iso,
        "first_unix": first_ts,
        "last_unix": last_ts,
        "host_span_s": (last_ts - first_ts) if first_ts is not None else None,
        "effective_sps": (rows / (last_ts - first_ts)) if last_ts and last_ts > first_ts else None,
        "unique_timestamps": unique_ts,
        "batch_size": {
            "mean": (rows / unique_ts) if unique_ts else None,
            "max": max(batch_hist) if batch_hist else 0,
            "top": dict(batch_hist.most_common(args.top)),
        },
        "timestamp_gaps": {
            "intervals": gap_count,
            "max_s": gap_max,
            "gt_0_05": gap_gt[0.05],
            "gt_0_1": gap_gt[0.1],
            "gt_0_5": gap_gt[0.5],
            "gt_1": gap_gt[1.0],
            "gt_5": gap_gt[5.0],
            "top": [
                {"gap_s": g, "before_unix": b, "after_unix": a}
                for g, b, a in sorted(gap_top, reverse=True)
            ],
        },
        "sample_sequence": {
            "normal_steps": normal_steps,
            "gap_events": seq_gap_events,
            "missing_total": missing_total,
            "duplicates": duplicates,
            "max_step": max_step,
            "missing_hist": {str(k): v for k, v in sorted(missing_hist.items())},
            "per_hour": per_hour,
        },
    }

    if args.meta:
        with open(args.meta, encoding="utf-8") as fh:
            meta = json.load(fh)
        out["meta"] = {
            "elapsed_s": meta.get("elapsed_s"),
            "frames": meta.get("frames"),
            "effective_sps": meta.get("effective_sps"),
            "run_error": meta.get("run_error"),
            "device_status_start": _status_counters(meta.get("device_status_start")),
            "device_status_end": _status_counters(meta.get("device_status_end")),
        }
        start = out["meta"]["device_status_start"]
        end = out["meta"]["device_status_end"]
        out["meta"]["device_counter_delta"] = {
            k: end.get(k, 0) - start.get(k, 0)
            for k in set(start) | set(end)
        }
        if meta.get("frames"):
            out["meta"]["host_minus_device_frames"] = rows - meta["frames"]

    json.dump(out, _out(), ensure_ascii=False, indent=2)
    _out().write("\n")


def _out():
    import sys
    return sys.stdout


if __name__ == "__main__":
    main()
