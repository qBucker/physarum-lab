#!/usr/bin/env python3
"""Analyse T7 pair-scan folders and print a pin-pair -> channel table.

Reads data/pinmap/<trial>/samples.csv written by host/pinmap_scan.py.
A true P/N pair shows one channel pinned near +/-expected mV with a small
standard deviation; floating channels sit on the rails (+/-187.5 mV).

Usage:
    python host/pinmap_analyze.py --indir data/pinmap --expected-mv 71
    python host/pinmap_analyze.py --indir data/pinmap --expected-mv 105
"""

import argparse
import csv
import os
import statistics

NV_PER_COUNT = 22.35   # ADS1299, gain 24, VREF 4.5 V
SKIP_SAMPLES = 125     # drop the first 0.5 s at 250 SPS


def load_stats(path, skip=SKIP_SAMPLES):
    cols = [[] for _ in range(8)]
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if i < skip:
                continue
            for k in range(8):
                cols[k].append(int(row["ch%d" % (k + 1)]))
    means = [statistics.mean(c) if c else float("nan") for c in cols]
    stds = [statistics.pstdev(c) if len(c) > 1 else float("nan") for c in cols]
    # counts -> mV
    means = [m * NV_PER_COUNT / 1e6 for m in means]
    stds = [s * NV_PER_COUNT / 1e6 for s in stds]
    return means, stds


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indir", default="data/pinmap")
    ap.add_argument("--baseline", default="baseline")
    ap.add_argument("--expected-mv", type=float, default=71.0)
    ap.add_argument("--ratio", type=float, default=0.25,
                    help="accept mean within expected*(1 +/- ratio)")
    ap.add_argument("--max-std-mv", type=float, default=5.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    indir = args.indir if os.path.isabs(args.indir) else os.path.join(root, args.indir)
    lo = args.expected_mv * (1.0 - args.ratio)
    hi = args.expected_mv * (1.0 + args.ratio)

    segments = sorted(d for d in os.listdir(indir)
                      if os.path.isdir(os.path.join(indir, d))
                      and d != args.baseline)
    lines = [
        "# T7 pair-scan analysis",
        "",
        "Expected differential %.0f mV; accept %.0f-%.0f mV with std < %.0f mV."
        % (args.expected_mv, lo, hi, args.max_std_mv),
        "",
        "| trial | hit ch | mean (mV) | std (mV) | verdict |",
        "|---|---|---:|---:|---|",
    ]
    found = {}
    for seg in segments:
        means, stds = load_stats(os.path.join(indir, seg, "samples.csv"))
        hits = [k for k in range(8)
                if lo <= abs(means[k]) <= hi and stds[k] <= args.max_std_mv]
        if len(hits) == 1:
            k = hits[0]
            verdict = "CH%d %s" % (k + 1, "+" if means[k] > 0 else "-")
            found[seg] = verdict
            lines.append("| %s | ch%d | %+.1f | %.1f | %s |" %
                         (seg, k + 1, means[k], stds[k], verdict))
        else:
            best = max(range(8), key=lambda k: abs(means[k]) if means[k] == means[k] else 0)
            verdict = "not a pair" if not hits else "ambiguous"
            lines.append("| %s | - | %+.1f (ch%d) | %.1f | %s |" %
                         (seg, means[best], best + 1, stds[best], verdict))

    lines += ["", "## Verdict summary", ""]
    for seg in segments:
        lines.append("%s: %s" % (seg, found.get(seg, "not a pair")))

    report = "\n".join(lines) + "\n"
    print(report)
    outpath = args.out or os.path.join(indir, "report.md")
    with open(outpath, "w") as fh:
        fh.write(report)
    print("wrote " + outpath)


if __name__ == "__main__":
    main()
