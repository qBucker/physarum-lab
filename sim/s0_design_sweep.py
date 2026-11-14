#!/usr/bin/env python3
"""S0 supplementary sweep: structural correlation time and drive period.

Fixes flicker = 10 uV (in-band) and scans the two design variables that the
first S0 run showed to be limiting:
  - tau_s: 0.5, 1, 2, 4 h (how fast the network remodels)
  - drive period: 0.5, 1, 2 h (how often we perturb)

Run:
    python3 s0_design_sweep.py --n-sims 40 --outdir results/s0_design
"""
from __future__ import annotations

import argparse
import csv
import json
import os

import numpy as np

from s0_detectability import run_cell, sha256

FLICKER_UV = 10.0
N_SURR = 200
RHO_GRID = [0.2, 0.3]
TAU_H = [0.5, 1.0, 2.0, 4.0]
DURATION_H = [24.0, 48.0]
DRIVE_PERIOD_H = [0.5, 1.0, 2.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=40)
    ap.add_argument("--n-surr", type=int, default=N_SURR)
    ap.add_argument("--outdir", default="results/s0_design")
    ap.add_argument("--base-seed", type=int, default=900)
    ap.add_argument("--driven-only", action="store_true")
    ap.add_argument("--spontaneous-only", action="store_true")
    ap.add_argument("--rho-grid", default=",".join(map(str, RHO_GRID)))
    ap.add_argument("--tau-grid", default=",".join(map(str, TAU_H)))
    ap.add_argument("--period-grid", default=",".join(map(str, DRIVE_PERIOD_H)))
    ap.add_argument("--duration-grid", default=",".join(map(str, DURATION_H)))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    rho_grid = [float(x) for x in args.rho_grid.split(",")]
    tau_grid = [float(x) for x in args.tau_grid.split(",")]
    period_grid = [float(x) for x in args.period_grid.split(",")]
    duration_grid = [float(x) for x in args.duration_grid.split(",")]

    cells = []
    counter = 0

    def add(mode, rho, dur, tau_h, period_h, drive_amp=2.0):
        nonlocal counter
        counter += 1
        base = args.base_seed * 1000 + counter * 100
        cell = run_cell(
            mode,
            rho,
            FLICKER_UV,
            dur,
            args.n_sims,
            base,
            n_surr=args.n_surr,
            signal_model="am",
            tau_s=tau_h * 3600.0,
            drive_period_s=(period_h * 3600.0) if period_h else 7200.0,
            drive_amp=drive_amp,
        )
        cells.append(cell)
        print(
            f"[{counter}] {mode:11s} tau={tau_h:.1f}h "
            f"period={period_h if period_h else '—'} rho={rho:.1f} "
            f"dur={dur:.0f}h -> power={cell['detection_rate']:.2f} "
            f"p_med={cell['median_p']:.3f}",
            flush=True,
        )

    # Null checks.
    if not args.spontaneous_only:
        add("driven", 0.0, max(duration_grid), 2.0, period_grid[0])
    if not args.driven_only:
        add("spontaneous", 0.0, max(duration_grid), 2.0, None)
        # Spontaneous: tau_s only (period irrelevant).
        for tau in tau_grid:
            for rho in rho_grid:
                for dur in duration_grid:
                    add("spontaneous", rho, dur, tau, None)

    # Driven: tau_s x period.
    if not args.spontaneous_only:
        for tau in tau_grid:
            for period in period_grid:
                for rho in rho_grid:
                    for dur in duration_grid:
                        add("driven", rho, dur, tau, period)

    json_path = os.path.join(args.outdir, "s0_design.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "flicker_uv": FLICKER_UV,
                    "n_sims": args.n_sims,
                    "n_surr": args.n_surr,
                    "base_seed": args.base_seed,
                    "signal_model": "am",
                },
                "cells": cells,
            },
            f,
            indent=2,
        )

    csv_path = os.path.join(args.outdir, "s0_design.csv")
    keys = [
        "mode", "rho", "tau_s", "drive_period_s", "duration_h", "n_sims",
        "detection_rate", "median_p", "median_lag_s", "lag_abs_error_s",
        "median_response_uv",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for c in cells:
            w.writerow({k: c.get(k, "") for k in keys})

    md_path = os.path.join(args.outdir, "s0_design.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# S0 design sweep: structural time scale and drive period\n\n")
        f.write("flicker = 10 uV in-band, AM model, 40 sims/cell, 200 surrogates.\n\n")
        f.write("| mode | rho | tau (h) | period (h) | duration (h) | power | median p |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for c in cells:
            period = f"{c['drive_period_s']/3600:.1f}" if c["drive_period_s"] else "—"
            f.write(
                f"| {c['mode']} | {c['rho']:.1f} | {c['tau_s']/3600:.1f} | "
                f"{period} | {c['duration_h']:.0f} | "
                f"{c['detection_rate']:.2f} | {c['median_p']:.3f} |\n"
            )

    meta = {
        "argv": vars(args),
        "outputs": {
            os.path.basename(p): sha256(p)
            for p in [json_path, csv_path, md_path]
        },
    }
    with open(os.path.join(args.outdir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote {args.outdir}")


if __name__ == "__main__":
    main()
