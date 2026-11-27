#!/usr/bin/env python3
"""T7 analog-header pin-mapping scan driver (pair mode).

The ADS1299 internal-test MUX disconnects the external header pins, so the
scan runs in `diff` mode (normal electrode input).  Each trial drives one
pin from a ~71 mV divider tap and ties the other pin to GND; only a true
P/N pair puts that channel in range at +/-71 mV, while floating channels
sit on the rails.

Usage:
    python host/pinmap_scan.py --port COM6 --layout rowwise
    python host/pinmap_scan.py --port COM6 --pairs 1-11,2-12,3-13

Injection (see protocols/bench-pinmap.md):
    3V3 - 10k - tap - 220R - GND, tap ~71 mV, Zout ~320R.
    Probe A: tap -> pin i ; probe B: GND -> pin j.

Notes:
- Numbering: top row 1-10, bottom row 11-20 (photograph the header first).
- Each trial reconfigures the board and opens its own folder under
  data/pinmap/, so every step stays auditable.
"""

import argparse
import os
import subprocess
import sys


def parse_pairs(text):
    pairs = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        a, b = part.split("-", 1)
        pairs.append((int(a), int(b)))
    return pairs


def gen_pairs(layout):
    if layout == "rowwise":          # top row 1-10, bottom row 11-20
        return [(i, i + 10) for i in range(1, 11)]
    if layout == "adjacent":         # 1-2, 3-4, ... 19-20
        return [(i, i + 1) for i in range(1, 20, 2)]
    if layout == "all":
        return [(i, j) for i in range(1, 21) for j in range(i + 1, 21)]
    raise SystemExit("unknown layout: " + layout)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--layout", default="rowwise",
                    choices=["rowwise", "adjacent", "all"])
    ap.add_argument("--pairs", default="", help="explicit list, e.g. 1-11,2-12")
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--outdir", default="data/pinmap")
    ap.add_argument("--mode", default="diff")
    ap.add_argument("--recorder", default="")
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    recorder = args.recorder or os.path.join(root, "host", "bcikit_openbci.py")
    if not os.path.isfile(recorder):
        sys.exit("recorder not found: " + recorder)
    outbase = args.outdir if os.path.isabs(args.outdir) else os.path.join(root, args.outdir)
    os.makedirs(outbase, exist_ok=True)

    pairs = parse_pairs(args.pairs) if args.pairs else gen_pairs(args.layout)

    def run(label, note):
        outdir = os.path.join(outbase, label)
        cmd = [sys.executable, recorder, "--port", args.port,
               "--mode", args.mode, "--duration", str(args.duration),
               "--outdir", outdir, "--label", label, "--note", note]
        print("$ " + " ".join(cmd))
        rc = subprocess.call(cmd)
        if rc != 0:
            sys.exit("recorder failed with exit code %d" % rc)

    print("T7 pin-mapping scan (pair mode, %s)" % args.mode)
    print("Injection: 3V3 - 10k - tap - 220R - GND  (tap ~71 mV).")
    print("Probe A: tap -> pin i ; probe B: GND -> pin j.")
    print("Numbering: top row 1-10, bottom row 11-20.")
    print()

    if not args.skip_baseline:
        input("Baseline: remove both probes, then press Enter...")
        run("baseline", "no probes connected")

    for i, j in pairs:
        label = "pair_%02d_%02d" % (i, j)
        input("Trial %s: probe A (71 mV) -> pin %d, probe B (GND) -> pin %d, "
              "then press Enter..." % (label, i, j))
        run(label, "71 mV on pin %d, GND on pin %d" % (i, j))
        input("Trial %s: disconnect both probes, then press Enter..." % label)

    print()
    print("Done. Analyse with:")
    print("    python " + os.path.join(root, "host", "pinmap_analyze.py") +
          " --indir " + args.outdir + " --expected-mv 71")


if __name__ == "__main__":
    main()
