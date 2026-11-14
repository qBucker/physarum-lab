#!/usr/bin/env python3
"""S0: detectability of structure-electrical coupling under realistic nuisances.

Pre-registered grid (do not edit after seeing results):
  rho          : 0.0, 0.1, 0.2, 0.3
  flicker_uv   : 1, 10, 30 uV RMS in the 0.01-0.1 Hz band
  duration_h   : 24, 48
  frame_dt     : 10 s
  modes        : spontaneous, driven (2 h square-wave drive)
  n_sims       : 40 per cell
  detection    : p < 0.05 against 200 surrogates

Outputs (in --outdir):
  s0_power.json      full results
  s0_power.csv       flat table
  s0_requirements.md summary + implied instrument requirements
  s0_power.png       power curves
  run_meta.json      parameters, seeds, SHA256 of outputs
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import asdict

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from instrument import ADCModel, ElectrodeModel, measure
from pipeline import detect_driven, detect_spontaneous
from truth import make_run

# ---------------------------------------------------------------------------
# Pre-registered grid
# ---------------------------------------------------------------------------
RHO_GRID = [0.0, 0.1, 0.2, 0.3]
FLICKER_GRID_UV = [1.0, 10.0, 30.0]
DURATION_GRID_H = [24.0, 48.0]
FRAME_DT_S = 10.0
MODES = ["spontaneous", "driven"]
N_SIMS = 40
N_SURR = 200
ALPHA = 0.05
LAG_S = 600.0
DRIVE_PERIOD_S = 7200.0
FS = 1.0
SIGNAL_UV = 20.0
DRIFT_MV_PER_H = 1.0
Z_SOURCE_OHM = 10e3

QUICK_RHO = [0.0, 0.2, 0.3]
QUICK_FLICKER = [10.0, 30.0]
QUICK_DURATION = [24.0]
QUICK_N = 8


def seed_for(mode_idx: int, rho_idx: int, flicker_idx: int, dur_idx: int, sim_idx: int) -> int:
    return (
        1_000_000
        + mode_idx * 100_000
        + rho_idx * 10_000
        + flicker_idx * 1_000
        + dur_idx * 100
        + sim_idx
    )


def run_cell(
    mode,
    rho,
    flicker_uv,
    duration_h,
    n_sims,
    base_seed,
    n_surr=N_SURR,
    signal_model="am",
    tau_s=7200.0,
    drive_period_s=DRIVE_PERIOD_S,
    drive_amp=1.0,
):
    if signal_model == "am":
        observable, f_lo, f_hi = "envelope", 0.02, 0.05
    elif signal_model == "potential":
        observable, f_lo, f_hi = "potential", 0.01, 0.1
    else:
        raise ValueError(signal_model)

    p_values = []
    lags = []
    responses = []
    for k in range(n_sims):
        seed = base_seed + k
        run = make_run(
            duration_s=duration_h * 3600.0,
            fs=FS,
            frame_dt=FRAME_DT_S,
            rho=rho,
            lag_s=LAG_S,
            tau_s=tau_s,
            mode=mode,
            drive_period_s=drive_period_s,
            drive_amp=drive_amp,
            signal_uv=SIGNAL_UV,
            signal_model=signal_model,
            seed=seed,
        )
        rng = np.random.default_rng(seed + 7_000_000)
        elec = ElectrodeModel(
            z_source_ohm=Z_SOURCE_OHM,
            drift_mv_per_h=DRIFT_MV_PER_H,
            flicker_uv_rms=flicker_uv,
        )
        adc = ADCModel(fs=FS, pga=8.0)
        e_obs = measure(run["e_mv"], run["t"], elec, adc, rng)

        if mode == "spontaneous":
            res = detect_spontaneous(
                e_obs,
                run["t"],
                run["s_obs"],
                run["t_s"],
                f_lo=f_lo,
                f_hi=f_hi,
                max_lag_s=1800.0,
                n_surr=n_surr,
                observable=observable,
                seed=seed + 11_000_000,
            )
            p_values.append(res["p"])
            lags.append(res["lag_s"])
        else:
            res = detect_driven(
                e_obs,
                run["t"],
                run["t_s"],
                period_s=drive_period_s,
                f_lo=f_lo,
                f_hi=f_hi,
                n_surr=n_surr,
                # Keep blocks long enough to preserve the envelope
                # autocorrelation, short enough to break the drive line.
                block_s=min(
                    max(3600.0, drive_period_s / 8.0),
                    drive_period_s / 4.0,
                    7200.0,
                ),
                observable=observable,
                seed=seed + 11_000_000,
            )
            p_values.append(res["p"])
            responses.append(res["response_uv"])

    p_values = np.asarray(p_values)
    out = {
        "mode": mode,
        "rho": rho,
        "flicker_uv": flicker_uv,
        "duration_h": duration_h,
        "tau_s": tau_s,
        "drive_period_s": drive_period_s if mode == "driven" else None,
        "n_sims": n_sims,
        "detection_rate": float(np.mean(p_values < ALPHA)),
        "mean_p": float(np.mean(p_values)),
        "median_p": float(np.median(p_values)),
    }
    if mode == "spontaneous":
        lags = np.asarray(lags)
        out["mean_lag_s"] = float(np.mean(lags))
        out["median_lag_s"] = float(np.median(lags))
        out["lag_abs_error_s"] = float(np.median(np.abs(np.abs(lags) - LAG_S)))
    else:
        responses = np.asarray(responses)
        out["mean_response_uv"] = float(np.mean(responses))
        out["median_response_uv"] = float(np.median(responses))
    return out


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small smoke-test grid")
    ap.add_argument("--n-sims", type=int, default=None)
    ap.add_argument("--n-surr", type=int, default=N_SURR)
    ap.add_argument("--outdir", default="results/s0")
    ap.add_argument("--base-seed", type=int, default=42)
    ap.add_argument(
        "--signal-model",
        choices=["am", "potential"],
        default="am",
        help="am = positive envelope of a narrowband oscillation; "
        "potential = signed slow potential",
    )
    ap.add_argument("--tau-s", type=float, default=2.0, help="structural correlation time (h)")
    ap.add_argument("--drive-period", type=float, default=2.0, help="drive period (h)")
    ap.add_argument("--drive-amp", type=float, default=1.0, help="drive amplitude (structural std units)")
    args = ap.parse_args()

    tau_s = args.tau_s * 3600.0
    drive_period_s = args.drive_period * 3600.0

    rho_grid = QUICK_RHO if args.quick else RHO_GRID
    flicker_grid = QUICK_FLICKER if args.quick else FLICKER_GRID_UV
    duration_grid = QUICK_DURATION if args.quick else DURATION_GRID_H
    n_sims = args.n_sims or (QUICK_N if args.quick else N_SIMS)

    os.makedirs(args.outdir, exist_ok=True)
    cells = []
    total = len(MODES) * len(rho_grid) * len(flicker_grid) * len(duration_grid)
    done = 0
    for mi, mode in enumerate(MODES):
        for ri, rho in enumerate(rho_grid):
            for fi, flicker in enumerate(flicker_grid):
                for di, dur in enumerate(duration_grid):
                    seed = seed_for(mi, ri, fi, di, args.base_seed)
                    cell = run_cell(
                        mode,
                        rho,
                        flicker,
                        dur,
                        n_sims,
                        seed,
                        n_surr=args.n_surr,
                        signal_model=args.signal_model,
                        tau_s=tau_s,
                        drive_period_s=drive_period_s,
                        drive_amp=args.drive_amp,
                    )
                    cells.append(cell)
                    done += 1
                    print(
                        f"[{done}/{total}] {mode:11s} rho={rho:.2f} "
                        f"flicker={flicker:5.1f}uV dur={dur:.0f}h "
                        f"-> power={cell['detection_rate']:.2f} "
                        f"p_med={cell['median_p']:.3f}",
                        flush=True,
                    )

    json_path = os.path.join(args.outdir, "s0_power.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "fs": FS,
                    "frame_dt_s": FRAME_DT_S,
                    "lag_s": LAG_S,
                    "tau_s": tau_s,
                    "drive_period_s": drive_period_s,
                    "drive_amp": args.drive_amp,
                    "signal_uv": SIGNAL_UV,
                    "drift_mv_per_h": DRIFT_MV_PER_H,
                    "z_source_ohm": Z_SOURCE_OHM,
                    "alpha": ALPHA,
                    "n_surr": args.n_surr,
                    "base_seed": args.base_seed,
                    "quick": args.quick,
                    "signal_model": args.signal_model,
                    "electrode": asdict(ElectrodeModel(z_source_ohm=Z_SOURCE_OHM)),
                    "adc": asdict(ADCModel(fs=FS, pga=8.0)),
                },
                "cells": cells,
            },
            f,
            indent=2,
        )

    csv_path = os.path.join(args.outdir, "s0_power.csv")
    keys = [
        "mode",
        "rho",
        "flicker_uv",
        "duration_h",
        "tau_s",
        "drive_period_s",
        "n_sims",
        "detection_rate",
        "mean_p",
        "median_p",
        "mean_lag_s",
        "median_lag_s",
        "lag_abs_error_s",
        "mean_response_uv",
        "median_response_uv",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for c in cells:
            w.writerow({k: c.get(k, "") for k in keys})

    # Power curves.
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, mode in zip(axes, MODES):
        sub = [c for c in cells if c["mode"] == mode]
        for flicker in flicker_grid:
            for dur in duration_grid:
                pts = [c for c in sub if c["flicker_uv"] == flicker and c["duration_h"] == dur]
                pts.sort(key=lambda c: c["rho"])
                ax.plot(
                    [c["rho"] for c in pts],
                    [c["detection_rate"] for c in pts],
                    marker="o",
                    label=f"{flicker:.0f} uV, {dur:.0f} h",
                )
        ax.axhline(ALPHA, color="k", ls=":", lw=1)
        ax.set_title(mode)
        ax.set_xlabel("coupling rho")
        ax.set_ylim(-0.02, 1.02)
    axes[0].set_ylabel("detection rate (p<0.05)")
    axes[1].legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    png_path = os.path.join(args.outdir, "s0_power.png")
    fig.savefig(png_path, dpi=160)
    plt.close(fig)

    # Summary table.
    md_path = os.path.join(args.outdir, "s0_requirements.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# S0 detectability — preliminary results\n\n")
        f.write("All numbers are **computed inside the model**; instrument parameters are\n")
        f.write("`assumed` until T1–T6. Detection = p < 0.05 vs 200 surrogates.\n\n")
        f.write(f"- signal model = {args.signal_model}\n")
        f.write(f"- fs = {FS} Hz, frame = {FRAME_DT_S} s, lag = {LAG_S} s, "
                f"drive period = {DRIVE_PERIOD_S} s, signal = {SIGNAL_UV} uV\n")
        f.write(f"- drift = {DRIFT_MV_PER_H} mV/h, source impedance = {Z_SOURCE_OHM:.0f} Ohm\n\n")
        f.write("| mode | rho | flicker (uV) | duration (h) | tau (h) | period (h) | power | median p | lag/response |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---|\n")
        for c in cells:
            if c["mode"] == "spontaneous":
                extra = f"lag {c['median_lag_s']:.0f} s (err {c['lag_abs_error_s']:.0f} s)"
            else:
                extra = f"resp {c['median_response_uv']:.1f} uV"
            period_h = (
                f"{c['drive_period_s']/3600:.1f}" if c["drive_period_s"] else "—"
            )
            f.write(
                f"| {c['mode']} | {c['rho']:.2f} | {c['flicker_uv']:.0f} | "
                f"{c['duration_h']:.0f} | {c['tau_s']/3600:.1f} | {period_h} | "
                f"{c['detection_rate']:.2f} | {c['median_p']:.3f} | {extra} |\n"
            )
        f.write("\n## Implied requirements\n\n")
        f.write("The binding constraints are the number of independent structural\n")
        f.write("states and the structural observation noise, not the ADC.  In-band\n")
        f.write("electrode flicker matters less because the structural signal is slow\n")
        f.write("and averages over fast flicker.\n")
        f.write("Read the minimum rho with power >= 0.8 at the highest tolerable flicker.\n")
        f.write("If no cell reaches 0.8, the experiment needs either longer duration,\n")
        f.write("driven perturbations, or a faster/less noisy structural observable.\n")

    meta = {
        "argv": vars(args),
        "outputs": {
            os.path.basename(p): sha256(p)
            for p in [json_path, csv_path, png_path, md_path]
        },
    }
    with open(os.path.join(args.outdir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote {args.outdir}")


if __name__ == "__main__":
    main()
