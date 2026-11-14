#!/usr/bin/env python3
"""R1: latent-pipeline recovery test in the S0 digital twin.

Question
--------
Given a known structure -> electrical coupling (strength rho, lag 600 s), does a
delay-embedded linear latent model (DMDc/ARX) recover (a) detection, (b)
direction, (c) lag, (d) strength -- and does it beat the S0 max-|r|
cross-correlation detector?

Pre-registered grid (do not edit after seeing results)
-----------------------------------------------------
rho              : 0.0, 0.2, 0.3
duration         : 48 h; fs 1 Hz; frame_dt 10 s
truth            : truth.make_run(signal_model="am", f0=0.03),
                   lag_s=600, tau_s=7200, tau_e=1800
observable       : Hilbert envelope in 0.02-0.05 Hz; log-envelope for the
                   latent model (linearises a = rho*s(t-lag) + noise)
instrument       : 10 uV flicker in 0.01-0.1 Hz, 1 mV/h drift,
                   10 kOhm source, ADC 1 SPS PGA 8
clean control    : post-hoc diagnostic (--clean): flicker=0, drift=0,
                   sigma_s_obs=0; not part of the pre-registered grid
latent model     : L=60 frames (10 min) delay embedding;
                   forward  e(t+1) ~ e(t..t-L+1) + s(t..t-L+1)
                   reverse  s(t+1) ~ s(t..t-L+1) + e(t..t-L+1)
split            : first 70% train, last 30% test, gap L frames
statistic        : out-of-sample R^2 gain over self-history-only baseline
null             : 50 phase-randomised surrogates (forward: s; reverse: e)
alpha            : 0.05
n_sims           : 30 per rho

Outputs (in --outdir):
  r1_results.json   full results
  r1_results.csv    flat table
  r1_summary.md     summary table + pre-registered metrics
  r1_summary.png    power / direction / lag figure
  run_meta.json     parameters, seeds, SHA256 of outputs
  SHA256SUMS
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from instrument import ADCModel, ElectrodeModel, measure
from pipeline import detect_spontaneous, extract_observable, phase_randomize
from truth import make_run

# ---------------------------------------------------------------------------
# Pre-registered grid
# ---------------------------------------------------------------------------
RHO_GRID = [0.0, 0.2, 0.3]
DURATION_H = 48.0
FS = 1.0
FRAME_DT = 10.0
LAG_S = 600.0
TAU_S = 7200.0
TAU_E = 1800.0
SIGNAL_UV = 20.0
FLICKER_UV = 10.0
DRIFT_MV_H = 1.0
Z_SOURCE_OHM = 10e3
N_SIMS = 30
N_SURR = 50
L_FRAMES = 60
TRAIN_FRAC = 0.7
ALPHA = 0.05
LAG_TOL_S = 120.0
RIDGE_FRAC = 1e-3


def seed_for(rho_idx: int, sim_idx: int) -> int:
    return 2_000_000 + rho_idx * 10_000 + sim_idx


def lag_matrix(x: np.ndarray, L: int) -> tuple[np.ndarray, np.ndarray]:
    """Rows t = L-1 .. n-2; columns k = 0..L-1 holding x[t-k]."""
    n = len(x)
    t = np.arange(L - 1, n - 1)
    X = x[t[:, None] - np.arange(L)[None, :]]
    return X, t


def fit_ridge(X: np.ndarray, y: np.ndarray, lam_frac: float = RIDGE_FRAC):
    """Ridge fit with centring; lambda is relative to mean X'X eigenvalue."""
    n, d = X.shape
    xm = X.mean(axis=0)
    ym = float(y.mean())
    Xc = X - xm
    yc = y - ym
    G = Xc.T @ Xc
    lam = lam_frac * np.trace(G) / d
    G.flat[:: d + 1] += lam
    coef = np.linalg.solve(G, Xc.T @ yc)
    return coef, xm, ym, lam


def predict_ridge(model, X: np.ndarray) -> np.ndarray:
    coef, xm, ym, _ = model
    return (X - xm) @ coef + ym


def r2_score(y: np.ndarray, pred: np.ndarray) -> float:
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def split_idx(n: int, L: int) -> tuple[np.ndarray, np.ndarray]:
    n_train = int(TRAIN_FRAC * n)
    tr = np.arange(0, n_train)
    te = np.arange(n_train + L, n)
    return tr, te


def analyze_one(seed: int, rho: float, n_surr: int, clean: bool = False) -> dict:
    rng = np.random.default_rng(seed + 7_000_000)

    flicker_uv = 0.0 if clean else FLICKER_UV
    drift_mv_h = 0.0 if clean else DRIFT_MV_H
    sigma_s_obs = 0.0 if clean else 0.3

    run = make_run(
        duration_s=DURATION_H * 3600.0,
        fs=FS,
        frame_dt=FRAME_DT,
        rho=rho,
        lag_s=LAG_S,
        tau_s=TAU_S,
        tau_e=TAU_E,
        signal_uv=SIGNAL_UV,
        signal_model="am",
        mode="spontaneous",
        sigma_s_obs=sigma_s_obs,
        seed=seed,
    )
    elec = ElectrodeModel(
        z_source_ohm=Z_SOURCE_OHM,
        drift_mv_per_h=drift_mv_h,
        flicker_uv_rms=flicker_uv,
    )
    adc = ADCModel(fs=FS, pga=8.0)
    e_obs = measure(run["e_mv"], run["t"], elec, adc, rng)

    env = extract_observable(e_obs, run["t"], 0.02, 0.05, "envelope")
    e_f = np.interp(run["t_s"], run["t"], env)
    e_f = np.log(np.maximum(e_f, 1e-9))
    s_f = np.asarray(run["s_obs"], dtype=float).copy()
    e_f = (e_f - e_f.mean()) / e_f.std(ddof=1)
    s_f = (s_f - s_f.mean()) / s_f.std(ddof=1)

    Xe, t_idx = lag_matrix(e_f, L_FRAMES)
    Xs, _ = lag_matrix(s_f, L_FRAMES)
    y_e = e_f[t_idx + 1]
    y_s = s_f[t_idx + 1]
    n = len(t_idx)
    tr, te = split_idx(n, L_FRAMES)

    # Forward: e(t+1) ~ e-history + s-history
    Xe_tr, Xe_te = Xe[tr], Xe[te]
    Xs_tr, Xs_te = Xs[tr], Xs[te]
    m0 = fit_ridge(Xe_tr, y_e[tr])
    m1 = fit_ridge(np.hstack([Xe_tr, Xs_tr]), y_e[tr])
    r2_f0 = r2_score(y_e[te], predict_ridge(m0, Xe_te))
    r2_f1 = r2_score(
        y_e[te], predict_ridge(m1, np.hstack([Xe_te, Xs_te]))
    )
    d_r2_f = r2_f1 - r2_f0

    # Reverse: s(t+1) ~ s-history + e-history
    m0r = fit_ridge(Xs_tr, y_s[tr])
    m1r = fit_ridge(np.hstack([Xs_tr, Xe_tr]), y_s[tr])
    r2_r0 = r2_score(y_s[te], predict_ridge(m0r, Xs_te))
    r2_r1 = r2_score(
        y_s[te], predict_ridge(m1r, np.hstack([Xs_te, Xe_te]))
    )
    d_r2_r = r2_r1 - r2_r0

    # Surrogate nulls (forward: break s; reverse: break e)
    null_f = np.empty(n_surr)
    null_r = np.empty(n_surr)
    y_e_te = y_e[te]
    y_s_te = y_s[te]
    for k in range(n_surr):
        s_s = phase_randomize(s_f, rng)
        Xs_s, _ = lag_matrix(s_s, L_FRAMES)
        ms = fit_ridge(np.hstack([Xe_tr, Xs_s[tr]]), y_e[tr])
        r2_s = r2_score(
            y_e_te, predict_ridge(ms, np.hstack([Xe_te, Xs_s[te]]))
        )
        null_f[k] = r2_s - r2_f0

        e_s = phase_randomize(e_f, rng)
        Xe_s, _ = lag_matrix(e_s, L_FRAMES)
        msr = fit_ridge(np.hstack([Xs_tr, Xe_s[tr]]), y_s[tr])
        r2_sr = r2_score(
            y_s_te, predict_ridge(msr, np.hstack([Xs_te, Xe_s[te]]))
        )
        null_r[k] = r2_sr - r2_r0

    p_f = (1.0 + float(np.sum(null_f >= d_r2_f))) / (1.0 + n_surr)
    p_r = (1.0 + float(np.sum(null_r >= d_r2_r))) / (1.0 + n_surr)

    # Lag from the forward full-model coefficient profile on the s block.
    coef = m1[0]
    s_coef = coef[L_FRAMES:]
    k_star = int(np.argmax(np.abs(s_coef)))
    lag_est_s = k_star * FRAME_DT

    # Strength: raw correlation at the estimated lag.  Do NOT use the partial
    # coefficient: the e(t) control absorbs the delayed structural copy, so the
    # partial coefficient is attenuated towards zero even when rho is large.
    strength_r = float(np.corrcoef(y_e, s_f[t_idx - k_star])[0, 1])

    # S0 baseline detector on the same simulated run.
    base = detect_spontaneous(
        e_obs,
        run["t"],
        s_f,
        run["t_s"],
        f_lo=0.02,
        f_hi=0.05,
        max_lag_s=1800.0,
        n_surr=n_surr,
        observable="envelope",
        seed=seed + 99,
    )

    return {
        "seed": int(seed),
        "rho": float(rho),
        "clean": bool(clean),
        "realized_r": float(run["truth"]["realized_r"]),
        "latent": {
            "d_r2_f": float(d_r2_f),
            "d_r2_r": float(d_r2_r),
            "p_f": float(p_f),
            "p_r": float(p_r),
            "lag_s": float(lag_est_s),
            "lag_abs_err_s": float(abs(lag_est_s - LAG_S)),
            "strength_r": strength_r,
            "n_train": int(len(tr)),
            "n_test": int(len(te)),
        },
        "baseline": {
            "p": float(base["p"]),
            "r": float(base["r"]),
            "lag_s": float(base["lag_s"]),
            "lag_abs_err_s": float(abs(base["lag_s"] - LAG_S)),
        },
    }


def summarize(records: list[dict]) -> dict:
    out = {}
    rhos = sorted({float(r["rho"]) for r in records})
    for rho in rhos:
        recs = [r for r in records if r["rho"] == rho]
        det = [r for r in recs if r["latent"]["p_f"] < ALPHA]
        det_r = [r for r in recs if r["latent"]["p_r"] < ALPHA]
        base_det = [r for r in recs if r["baseline"]["p"] < ALPHA]

        def frac(xs):
            return float(len(xs)) / len(recs) if recs else float("nan")

        out[str(rho)] = {
            "n": len(recs),
            "latent_power": frac(det),
            "latent_reverse_power": frac(det_r),
            "baseline_power": frac(base_det),
            "direction_correct": (
                float(np.mean([r["latent"]["d_r2_f"] > r["latent"]["d_r2_r"] for r in det]))
                if det
                else float("nan")
            ),
            "lag_recovered": (
                float(np.mean([r["latent"]["lag_abs_err_s"] <= LAG_TOL_S for r in det]))
                if det
                else float("nan")
            ),
            "lag_median_s": (
                float(np.median([r["latent"]["lag_s"] for r in det])) if det else float("nan")
            ),
            "strength_median_r": (
                float(np.median([r["latent"]["strength_r"] for r in det]))
                if det
                else float("nan")
            ),
            "strength_median_realized_r": (
                float(np.median([r["realized_r"] for r in det])) if det else float("nan")
            ),
            "baseline_lag_recovered": (
                float(np.mean([r["baseline"]["lag_abs_err_s"] <= LAG_TOL_S for r in base_det]))
                if base_det
                else float("nan")
            ),
            "baseline_lag_median_s": (
                float(np.median([r["baseline"]["lag_s"] for r in base_det]))
                if base_det
                else float("nan")
            ),
            "baseline_direction_correct": (
                float(np.mean([r["baseline"]["lag_s"] > 0 for r in base_det]))
                if base_det
                else float("nan")
            ),
            "baseline_median_r": (
                float(np.median([r["baseline"]["r"] for r in base_det]))
                if base_det
                else float("nan")
            ),
        }
    return out


def write_outputs(records, summary, outdir, args):
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir, "r1_results.json"), "w") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2)

    fields = [
        "rho", "seed", "realized_r",
        "latent_p_f", "latent_p_r", "latent_d_r2_f", "latent_d_r2_r",
        "latent_lag_s", "latent_lag_abs_err_s", "latent_strength_r",
        "baseline_p", "baseline_r", "baseline_lag_s", "baseline_lag_abs_err_s",
    ]
    with open(os.path.join(outdir, "r1_results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            w.writerow({
                "rho": r["rho"],
                "seed": r["seed"],
                "realized_r": r["realized_r"],
                "latent_p_f": r["latent"]["p_f"],
                "latent_p_r": r["latent"]["p_r"],
                "latent_d_r2_f": r["latent"]["d_r2_f"],
                "latent_d_r2_r": r["latent"]["d_r2_r"],
                "latent_lag_s": r["latent"]["lag_s"],
                "latent_lag_abs_err_s": r["latent"]["lag_abs_err_s"],
                "latent_strength_r": r["latent"]["strength_r"],
                "baseline_p": r["baseline"]["p"],
                "baseline_r": r["baseline"]["r"],
                "baseline_lag_s": r["baseline"]["lag_s"],
                "baseline_lag_abs_err_s": r["baseline"]["lag_abs_err_s"],
            })

    # Figure: power vs rho; direction/lag recovery bars at rho=0.3.
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4), dpi=140)
    rhos = sorted(float(x) for x in summary.keys())
    axes[0].plot(rhos, [summary[str(r)]["latent_power"] for r in rhos],
                 "o-", label="latent DMDc (forward)")
    axes[0].plot(rhos, [summary[str(r)]["baseline_power"] for r in rhos],
                 "s--", label="S0 max-|r| detector")
    axes[0].plot(rhos, [summary[str(r)]["latent_reverse_power"] for r in rhos],
                 "^:", label="latent (reverse)")
    axes[0].set_xlabel("rho (model parameter)")
    axes[0].set_ylabel("detection rate (p < 0.05)")
    axes[0].set_ylim(-0.03, 1.03)
    axes[0].grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    axes[0].set_title("Detection")

    top = summary[str(max(rhos))]
    metrics = [
        ("direction\ncorrect", top["direction_correct"]),
        ("lag within\n±120 s", top["lag_recovered"]),
        ("baseline lag\nwithin ±120 s", top["baseline_lag_recovered"]),
    ]
    axes[1].barh([m[0] for m in metrics], [m[1] for m in metrics], color=["C0", "C0", "C1"])
    axes[1].set_xlim(0.0, 1.05)
    axes[1].set_xlabel("fraction of detected runs (rho=0.3)")
    axes[1].grid(alpha=0.3, axis="x")
    axes[1].set_title("Direction and lag recovery")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "r1_summary.png"))

    # Summary markdown
    with open(os.path.join(outdir, "r1_summary.md"), "w") as f:
        f.write("# R1 — latent-pipeline recovery in the S0 digital twin\n\n")
        if getattr(args, "clean", False):
            f.write("**Clean control (post-hoc diagnostic): no flicker, drift, or "
                    "structural observation noise.**\n\n")
        f.write("Evidence label: **computed (model-internal)**. `rho` is a model "
                "parameter, not a biological measurement; no experimental claim.\n\n")
        f.write("| rho | n | latent power | latent reverse power | baseline power | "
                "direction correct | lag ±120 s | lag median | baseline lag ±120 s | "
                "baseline lag median | r at lag median | realized r median |\n")
        f.write("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in sorted(float(x) for x in summary.keys()):
            s = summary[str(r)]
            f.write(
                f"| {r:.1f} | {s['n']} | {s['latent_power']:.3f} | "
                f"{s['latent_reverse_power']:.3f} | {s['baseline_power']:.3f} | "
                f"{s['direction_correct']:.3f} | {s['lag_recovered']:.3f} | "
                f"{s['lag_median_s']:.0f} | {s['baseline_lag_recovered']:.3f} | "
                f"{s['baseline_lag_median_s']:.0f} | {s['strength_median_r']:.3f} | "
                f"{s['strength_median_realized_r']:.3f} |\n"
            )
        f.write("\nPre-registered tolerance: |lag − 600 s| ≤ 120 s; alpha = 0.05; "
                "phase-randomised surrogates; n per rho as listed in the table.\n")

    meta = {
        "script": os.path.basename(__file__),
        "python": os.sys.version,
        "numpy": np.__version__,
        "args": vars(args),
        "constants": {
            "RHO_GRID": RHO_GRID,
            "DURATION_H": DURATION_H,
            "FS": FS,
            "FRAME_DT": FRAME_DT,
            "LAG_S": LAG_S,
            "TAU_S": TAU_S,
            "TAU_E": TAU_E,
            "SIGNAL_UV": SIGNAL_UV,
            "FLICKER_UV": FLICKER_UV,
            "DRIFT_MV_H": DRIFT_MV_H,
            "Z_SOURCE_OHM": Z_SOURCE_OHM,
            "N_SIMS": N_SIMS,
            "N_SURR": N_SURR,
            "L_FRAMES": L_FRAMES,
            "TRAIN_FRAC": TRAIN_FRAC,
            "ALPHA": ALPHA,
            "LAG_TOL_S": LAG_TOL_S,
            "RIDGE_FRAC": RIDGE_FRAC,
        },
    }
    with open(os.path.join(outdir, "run_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # SHA256SUMS (excluding itself)
    lines = []
    for name in sorted(os.listdir(outdir)):
        if name == "SHA256SUMS":
            continue
        path = os.path.join(outdir, name)
        if os.path.isfile(path):
            h = hashlib.sha256(open(path, "rb").read()).hexdigest()
            lines.append(f"{h}  {name}")
    with open(os.path.join(outdir, "SHA256SUMS"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="results/r1_latent_recovery")
    ap.add_argument("--n-sims", type=int, default=N_SIMS)
    ap.add_argument("--n-surr", type=int, default=N_SURR)
    ap.add_argument("--rho-grid", type=str, default=",".join(str(r) for r in RHO_GRID))
    ap.add_argument("--pilot", action="store_true", help="one run per rho, print diagnostics")
    ap.add_argument(
        "--clean",
        action="store_true",
        help="clean control: no flicker, drift, or structural observation noise",
    )
    args = ap.parse_args()

    rho_grid = [float(x) for x in args.rho_grid.split(",")]
    t0 = time.time()
    records = []
    for ri, rho in enumerate(rho_grid):
        n_sims = 1 if args.pilot else args.n_sims
        for k in range(n_sims):
            seed = seed_for(ri, k)
            rec = analyze_one(seed, rho, args.n_surr, clean=args.clean)
            records.append(rec)
            print(
                f"rho={rho:.1f} seed={seed} "
                f"p_f={rec['latent']['p_f']:.3f} p_r={rec['latent']['p_r']:.3f} "
                f"dR2_f={rec['latent']['d_r2_f']:+.4f} dR2_r={rec['latent']['d_r2_r']:+.4f} "
                f"lag={rec['latent']['lag_s']:.0f}s r_lag={rec['latent']['strength_r']:+.3f} "
                f"realized_r={rec['realized_r']:+.3f} "
                f"base_p={rec['baseline']['p']:.3f} base_lag={rec['baseline']['lag_s']:.0f}s",
                flush=True,
            )
    summary = summarize(records)
    write_outputs(records, summary, args.outdir, args)
    print(f"\nwrote {args.outdir} in {time.time() - t0:.1f} s")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
