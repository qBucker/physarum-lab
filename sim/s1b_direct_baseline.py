#!/usr/bin/env python3
"""S1b: direct nonlinear baseline for the S1 testbed.

Question
--------
S1 (2026-11-14) reported that the quadratic latent detector S1-L2 beats the
direct *linear* detectors D1/D2 on the quadratic-coupling cell.  The missing
control is a **direct nonlinear detector**: the same quadratic library on raw
observations, with no geometry POD and no electrical PCA.  S1b asks whether
the S1-L2 gain comes from the latent representation (POD/PCA + delayed-gain)
or merely from having quadratic features at the right lag.

Pre-registered design (do not edit after seeing results)
-------------------------------------------------------
Primary cell
  coupling     : quadratic
  rho          : 0.9
  n_sims       : 30, same seeds as the S1 primary grid
  signal       : 100 uV carrier, 10 uV in-band flicker
  camera       : 24 x 20 pixels, noise 0.03, training-segment POD
  lag          : 600 s
  surrogates   : 50 common-phase, per detector
  alpha        : 0.05
Specificity cell
  coupling     : linear, rho = 0.9, n = 30, same seeds as S1
Null cells
  rho          : 0.0, both couplings, n = 30 each (60 total), same seeds as S1
  used for empirical FPR and threshold matching, exactly as S1.

Detectors (all use the same estimator s1.partial_delayed_gain, quadratic=True)
  S1-L2 : Ee   (3 electrical PCs)      x G  (8 geometry POD modes)
  DQ-A  : Eraw (16 raw electrode ch.)  x Gr (8 region means, 4 x 2 grid)
  DQ-C  : Eraw x G          (isolates the electrical PCA)
  DQ-D  : Ee   x Gr         (isolates the geometry POD)
  DQ-A is the pre-registered direct nonlinear baseline ("raw electrodes +
  raw geometry summary").  DQ-C/D are the 2 x 2 decomposition controls.

Statistic
  The same partial delayed-quadratic gain as S1: for each target block Y,
  compare
      Y(t) ~ [X(t), Q(X(t)), X(t-600)]
  with
      Y(t) ~ [X(t), Q(X(t)), X(t-600), Q(X(t-600))]
  and take the mean R^2 gain over targets.  The common-phase surrogate
  randomises the geometry block and refits the whole model.

Matched-FPR rule
  If any primary detector's rho=0 FPR is outside [0.02, 0.10], the decision
  uses each detector's empirical 95th-percentile gain threshold from the
  60 null runs; otherwise it uses the nominal p < 0.05 rate.  Both are
  reported in all cases.

Decision rule (pre-registered)
  Let p_s1 = S1-L2 detection rate in the quadratic cell, p_dq = DQ-A rate.
  * LATENT REPRESENTATION ADDS VALUE if p_s1 - p_dq >= 0.20, with a
    positive paired discordance (S1-L2 detects where DQ-A does not).
  * QUADRATIC FEATURES EXPLAIN THE GAIN if p_dq >= p_s1 - 0.10.
  * INCONCLUSIVE otherwise.
  The 2 x 2 table is descriptive: compare S1-L2 with DQ-C (electrical PCA
  effect at fixed POD geometry) and with DQ-D (geometry POD effect at fixed
  electrical PCs).
  Specificity check: if DQ-A also detects the linear cell at >= 0.20, the
  direct quadratic baseline is not specific to the nonlinear cell; report it
  and do not use a "latent wins" verdict on its own.

Secondary grid (pre-registered, descriptive)
  * low-signal: 20 uV carrier, quadratic rho=0.9, n=20 + rho=0 null n=20;
  * noisy-camera: camera noise 0.10, quadratic rho=0.9, n=20 + null n=20.
  These test whether the primary ranking survives the S0-realistic carrier
  and a noisier camera.  They do not enter the primary verdict.

Outputs (in --outdir)
  s1b_results.json / s1b_results.csv
  s1b_summary.md
  s1b_power.png
  run_meta.json
  SHA256SUMS

Reproduce
  cd physarum-lab/sim
  OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 \
      python3 s1b_direct_baseline.py --grid all --outdir results/s1b_direct_baseline
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np
from scipy.stats import binomtest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import s1_network_testbed as s1

BASE = Path(__file__).resolve().parent
OUT_RESULTS = BASE / "results" / "s1_network" / "s1_results.json"

# Pre-registered constants
RHO_PRIMARY = 0.9
N_SIMS = 30
N_SURR = 50
ALPHA = 0.05
SIGNAL_UV = 100.0
CAMERA_NOISE = 0.03
REGION_GRID = (4, 2)          # 4 columns x 2 rows = 8 region means
N_REGIONS = REGION_GRID[0] * REGION_GRID[1]
DETECTORS = ("s1l2", "dqa", "dqc", "dqd")
FPR_LO = 0.02
FPR_HI = 0.10
MARGIN_KEEP = 0.20
MARGIN_DIRECT = 0.10
SECONDARY_N = 20


def region_matrix() -> np.ndarray:
    """8 block averages over the 24 x 20 camera image (row-major pixels)."""
    height, width = s1.CAMERA_PIX
    gh, gw = REGION_GRID
    pixels = np.arange(height * width).reshape(height, width)
    R = np.zeros((gh * gw, height * width))
    for r in range(gh):
        rows = slice(r * height // gh, (r + 1) * height // gh)
        for c in range(gw):
            cols = slice(c * width // gw, (c + 1) * width // gw)
            idx = pixels[rows, cols].ravel()
            R[r * gw + c, idx] = 1.0 / len(idx)
    return R


R_MATRIX = region_matrix()


def prepare(seed: int, coupling: str, rho: float,
            signal_uv: float | None = None,
            camera_noise: float | None = None) -> dict:
    """Replicate the S1 run_one observation chain and add raw blocks."""
    old_signal = s1.SIGNAL_UV
    old_noise = s1.CAMERA_NOISE
    if signal_uv is not None:
        s1.SIGNAL_UV = float(signal_uv)
    if camera_noise is not None:
        s1.CAMERA_NOISE = float(camera_noise)
    try:
        truth = s1.simulate_network(seed)
        graph, D = truth["graph"], truth["D"]
        n = D.shape[1]
        ntr = int(s1.TRAIN_FRAC * n)

        mu_d = D[:, :ntr].mean(axis=1, keepdims=True)
        sd_d = D[:, :ntr].std(axis=1, ddof=1, keepdims=True)
        h = (D - mu_d) / np.maximum(sd_d, 1e-30)
        W = s1.camera_weights(graph["pts"], graph["edges"])
        rng_cam = np.random.default_rng(seed + 3)
        image = (h.T @ W.T) + s1.CAMERA_NOISE * rng_cam.normal(
            size=(n, len(W)))
        pod = s1.pod_scores(image)
        G = pod["G"]

        Gr = image @ R_MATRIX.T
        mu_r = Gr[:ntr].mean(axis=0)
        sd_r = np.maximum(Gr[:ntr].std(axis=0, ddof=1), 1e-30)
        Gr = (Gr - mu_r) / sd_r

        elec = s1.electrical_observation(
            seed, graph, D, coupling, rho, s1.ELEC_K, clean=False)
        Ee = elec["Ee"]
        Eraw = elec["env_z"].T
        return {
            "seed": int(seed),
            "G": G,
            "Gr": Gr,
            "Ee": Ee,
            "Eraw": Eraw,
            "r": pod["r"],
        }
    finally:
        s1.SIGNAL_UV = old_signal
        s1.CAMERA_NOISE = old_noise


def run_detectors(prep: dict, n_surr: int) -> dict:
    seed = prep["seed"]
    rngs = {
        "s1l2": np.random.default_rng(seed + 13),  # same stream as S1 L2
        "dqa": np.random.default_rng(seed + 21),
        "dqc": np.random.default_rng(seed + 22),
        "dqd": np.random.default_rng(seed + 23),
    }
    specs = {
        "s1l2": (prep["Ee"], prep["G"]),
        "dqa": (prep["Eraw"], prep["Gr"]),
        "dqc": (prep["Eraw"], prep["G"]),
        "dqd": (prep["Ee"], prep["Gr"]),
    }
    out = {}
    for det in DETECTORS:
        Y, X = specs[det]
        res = s1.partial_delayed_gain(Y, X, n_surr, rngs[det],
                                      quadratic=True)
        out[det] = {"gain": float(res["gain"]), "p": float(res["p"])}
    return out


def analyze_cell(coupling: str, rho: float, n_sims: int, n_surr: int,
                 signal_uv: float, camera_noise: float) -> list[dict]:
    records = []
    for sim in range(n_sims):
        seed = s1.seed_for("primary", coupling, s1.ELEC_K, sim, rho)
        prep = prepare(seed, coupling, rho, signal_uv, camera_noise)
        det = run_detectors(prep, n_surr)
        rec = {
            "seed": int(seed),
            "coupling": coupling,
            "rho": float(rho),
            "signal_uv": float(signal_uv),
            "camera_noise": float(camera_noise),
            "pod_r": int(prep["r"]),
        }
        for d in DETECTORS:
            rec[f"{d}_gain"] = det[d]["gain"]
            rec[f"{d}_p"] = det[d]["p"]
        records.append(rec)
    return records


def cell_summary(records: list[dict],
                 include_conditions: bool = False) -> dict:
    def key_of(r):
        if include_conditions:
            return (r["coupling"], r["rho"], r["signal_uv"], r["camera_noise"])
        return (r["coupling"], r["rho"])

    out = {}
    for key in sorted({key_of(r) for r in records}):
        recs = [r for r in records if key_of(r) == key]
        n = len(recs)
        cell = {"n": n}
        for d in DETECTORS:
            det = [r for r in recs if r[f"{d}_p"] < ALPHA]
            cell[d] = {
                "power": len(det) / n if n else float("nan"),
                "detected": len(det),
                "median_gain": float(np.median(
                    [r[f"{d}_gain"] for r in recs])) if recs else float("nan"),
            }
        if include_conditions:
            coupling, rho, signal, camera = key
            label = (f"{coupling}|{rho:.1f}|{signal:.0f}uV|cam{camera:.2f}")
        else:
            coupling, rho = key
            label = f"{coupling}|{rho:.1f}"
        out[label] = cell
    return out


def null_stats(records: list[dict]) -> dict:
    nulls = [r for r in records if r["rho"] == 0.0]
    out = {}
    for d in DETECTORS:
        vals = [r[f"{d}_gain"] for r in nulls]
        det = [r for r in nulls if r[f"{d}_p"] < ALPHA]
        out[d] = {
            "n": len(nulls),
            "fpr": len(det) / len(nulls) if nulls else float("nan"),
            "threshold": float(np.quantile(vals, 0.95)) if vals
            else float("nan"),
        }
    return out


def matched_power(records: list[dict], nulls: dict) -> dict:
    out = {}
    for coupling, rho in sorted({(r["coupling"], r["rho"]) for r in records}):
        if rho == 0.0:
            continue
        recs = [r for r in records if r["coupling"] == coupling
                and r["rho"] == rho]
        cell = {}
        for d in DETECTORS:
            cell[d] = float(np.mean(
                [r[f"{d}_gain"] >= nulls[d]["threshold"] for r in recs]))
        out[f"{coupling}|{rho:.1f}"] = cell
    return out


def paired_test(records: list[dict], a: str, b: str,
                coupling: str = "quadratic", rho: float = RHO_PRIMARY) -> dict:
    recs = [r for r in records if r["coupling"] == coupling
            and r["rho"] == rho]
    a_det = np.array([r[f"{a}_p"] < ALPHA for r in recs], bool)
    b_det = np.array([r[f"{b}_p"] < ALPHA for r in recs], bool)
    b_only = int(np.sum(a_det & ~b_det))
    c_only = int(np.sum(~a_det & b_det))
    if b_only + c_only == 0:
        p = 1.0
    else:
        p = float(binomtest(b_only, b_only + c_only, 0.5).pvalue)
    return {
        "a": a, "b": b,
        f"{a}_only": b_only,
        f"{b}_only": c_only,
        "both": int(np.sum(a_det & b_det)),
        "neither": int(np.sum(~a_det & ~b_det)),
        "sign_test_p": p,
    }


def decide(primary: dict, nulls: dict, matched: dict,
           paired: dict) -> dict:
    cell = primary[f"quadratic|{RHO_PRIMARY:.1f}"]
    linear_key = f"linear|{RHO_PRIMARY:.1f}"
    linear = primary.get(linear_key, {})
    fpr = {d: nulls[d]["fpr"] for d in DETECTORS}
    use_matched = any(not (FPR_LO <= fpr[d] <= FPR_HI) for d in DETECTORS)
    if use_matched:
        p_s1 = matched[f"quadratic|{RHO_PRIMARY:.1f}"]["s1l2"]
        p_dq = matched[f"quadratic|{RHO_PRIMARY:.1f}"]["dqa"]
    else:
        p_s1 = cell["s1l2"]["power"]
        p_dq = cell["dqa"]["power"]

    dqa_linear = linear.get("dqa", {}).get("power", float("nan"))
    specific = not (np.isfinite(dqa_linear) and dqa_linear >= 0.20)

    if p_s1 - p_dq >= MARGIN_KEEP and specific:
        status = ("LATENT REPRESENTATION ADDS VALUE: S1-L2 beats the direct "
                  "nonlinear baseline DQ-A by >= 0.20 at matched FPR")
    elif p_dq >= p_s1 - MARGIN_DIRECT:
        status = ("QUADRATIC FEATURES EXPLAIN THE GAIN: the direct nonlinear "
                  "baseline DQ-A matches or exceeds S1-L2; no evidence for a "
                  "latent-representation advantage")
    else:
        status = ("INCONCLUSIVE: the S1-L2 / DQ-A difference is between the "
                  "pre-registered margins")
    if not specific:
        status += ("; NOTE: DQ-A also detects the linear cell (>= 0.20), so "
                   "the direct quadratic baseline is not specific to the "
                   "nonlinear cell")
    return {
        "status": status,
        "use_matched_thresholds": bool(use_matched),
        "p_s1l2": float(p_s1),
        "p_dqa": float(p_dq),
        "difference": float(p_s1 - p_dq),
        "fpr": fpr,
        "dqa_linear_power": float(dqa_linear),
        "dqa_specific": bool(specific),
        "paired_s1l2_vs_dqa": paired,
        "decomposition": {
            "s1l2": "3 PCs x 8 POD",
            "dqc": "16 raw electrodes x 8 POD",
            "dqd": "3 PCs x 8 region means",
            "dqa": "16 raw electrodes x 8 region means",
        },
    }


def s1_reference_check(primary_records: list[dict]) -> dict:
    """Compare the S1b S1-L2 p-values with the frozen S1 evidence."""
    if not OUT_RESULTS.exists():
        return {"available": False}
    ref = json.load(open(OUT_RESULTS))["records"]
    ref_map = {(r["seed"], r["coupling"], r["rho"]): r["l2"]["p_f"]
               for r in ref}
    diffs = []
    missing = 0
    for r in primary_records:
        key = (r["seed"], r["coupling"], r["rho"])
        if key not in ref_map:
            missing += 1
            continue
        diffs.append(abs(r["s1l2_p"] - ref_map[key]))
    return {
        "available": True,
        "n_paired": len(diffs),
        "missing": missing,
        "max_abs_p_diff": float(max(diffs)) if diffs else float("nan"),
        "s1_reference_note": ("S1-L2 in S1b is recomputed with the same seed "
                              "and surrogate stream; small differences can "
                              "arise from the ARPACK POD starting vector."),
    }


def write_outputs(records: list[dict], outdir: str, args, runtime_s: float):
    os.makedirs(outdir, exist_ok=True)
    primary = [r for r in records if r["signal_uv"] == SIGNAL_UV
               and r["camera_noise"] == CAMERA_NOISE]
    secondary = [r for r in records if r not in primary]
    primary_summary = cell_summary(primary)
    primary_nulls = null_stats(primary)
    primary_matched = matched_power(primary, primary_nulls)
    paired = paired_test(primary, "s1l2", "dqa")
    decision = decide(primary_summary, primary_nulls, primary_matched,
                      paired) if f"quadratic|{RHO_PRIMARY:.1f}" in primary_summary else {}
    ref_check = s1_reference_check(primary)
    secondary_summary = (cell_summary(secondary, include_conditions=True)
                         if secondary else {})

    with open(os.path.join(outdir, "s1b_results.json"), "w") as f:
        json.dump({
            "primary": {"summary": primary_summary, "nulls": primary_nulls,
                        "matched_power": primary_matched,
                        "paired": paired, "decision": decision,
                        "s1_reference_check": ref_check},
            "secondary": {"summary": secondary_summary},
            "records": records,
        }, f, indent=2)

    fields = ["seed", "coupling", "rho", "signal_uv", "camera_noise", "pod_r"]
    for d in DETECTORS:
        fields += [f"{d}_gain", f"{d}_p"]
    with open(os.path.join(outdir, "s1b_results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            w.writerow({k: r[k] for k in fields})

    # Figure: primary cell power, linear specificity, FPR.
    if primary_summary:
        fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.6), dpi=180)
        labels = {"s1l2": "S1-L2\nPC+POD", "dqa": "DQ-A\nraw+region",
                  "dqc": "DQ-C\nraw+POD", "dqd": "DQ-D\nPC+region"}
        colors = ["#7c3aed", "#eb6834", "#2a78d6", "#1baf7a"]
        x = np.arange(len(DETECTORS))
        for ax, key, title in (
            (axes[0], f"quadratic|{RHO_PRIMARY:.1f}", "quadratic (primary)"),
            (axes[1], f"linear|{RHO_PRIMARY:.1f}", "linear (specificity)"),
        ):
            cell = primary_summary.get(key, {})
            ys = [cell.get(d, {}).get("power", np.nan) for d in DETECTORS]
            ax.bar(x, ys, color=colors, width=0.65)
            for xi, y in zip(x, ys):
                if np.isfinite(y):
                    ax.text(xi, y + 0.03, f"{y:.2f}", ha="center",
                            va="bottom", fontsize=8, color="#52514e")
            ax.set_xticks(x)
            ax.set_xticklabels([labels[d] for d in DETECTORS], fontsize=8)
            ax.set_ylim(0, 1.1)
            ax.set_ylabel("detection rate (p < 0.05)")
            ax.set_title(title, fontsize=10, loc="left")
            ax.grid(alpha=0.25, axis="y")
            ax.set_axisbelow(True)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "s1b_power.png"))
        plt.close(fig)

    with open(os.path.join(outdir, "s1b_summary.md"), "w") as f:
        f.write("# S1b — direct nonlinear baseline\n\n")
        f.write("Evidence label: **computed (model-internal)**. `rho` is a "
                "model parameter, not a biological measurement.\n\n")
        f.write("Pre-registered: see the module docstring and "
                f"`run_meta.json`; alpha = 0.05, surrogates = {args.n_surr}, "
                f"lag = 600 s.\n\n")
        f.write("## Primary cell (rho = 0.9, quadratic, 100 uV, camera 0.03)\n\n")
        f.write("| detector | power (nominal) | power (matched) | linear-cell "
                "power | FPR |\n|---|---:|---:|---:|---:|\n")
        qkey = f"quadratic|{RHO_PRIMARY:.1f}"
        lkey = f"linear|{RHO_PRIMARY:.1f}"
        for d in DETECTORS:
            f.write(
                f"| {d.upper()} | {primary_summary[qkey][d]['power']:.3f} | "
                f"{primary_matched[qkey][d]:.3f} | "
                f"{primary_summary[lkey][d]['power']:.3f} | "
                f"{primary_nulls[d]['fpr']:.3f} |\n")
        f.write("\n## Decision\n\n")
        f.write(f"- Status: **{decision.get('status', 'missing')}**\n")
        f.write(f"- p(S1-L2) = {decision.get('p_s1l2', float('nan')):.3f}; "
                f"p(DQ-A) = {decision.get('p_dqa', float('nan')):.3f}; "
                f"difference = {decision.get('difference', float('nan')):+.3f}\n")
        f.write(f"- Matched thresholds used: "
                f"{decision.get('use_matched_thresholds')}\n")
        f.write(f"- Paired S1-L2 vs DQ-A: {json.dumps(paired)}\n")
        f.write(f"- S1 reference check: {json.dumps(ref_check)}\n")
        if secondary_summary:
            f.write("\n## Secondary grid (descriptive)\n\n")
            f.write("| cell | n | S1-L2 | DQ-A | DQ-C | DQ-D |\n")
            f.write("|---|---:|---:|---:|---:|---:|\n")
            for key in sorted(secondary_summary):
                c = secondary_summary[key]
                f.write(f"| {key} | {c['n']} | "
                        f"{c['s1l2']['power']:.3f} | "
                        f"{c['dqa']['power']:.3f} | "
                        f"{c['dqc']['power']:.3f} | "
                        f"{c['dqd']['power']:.3f} |\n")
        f.write("\n## Notes\n\n")
        f.write("- DQ-A is the pre-registered direct nonlinear baseline: "
                "16 raw electrode channels x 8 region means (4 x 2 grid), "
                "same quadratic library and estimator as S1-L2.\n")
        f.write("- DQ-C and DQ-D isolate the electrical PCA and the geometry "
                "POD respectively.\n")
        f.write("- The 600 s lag is pre-registered; all detectors use the "
                "same lag.\n")
        f.write("- The testbed is not a biological claim; S1b does not "
                "replace the four experimental controls.\n")

    meta = {
        "script": os.path.basename(__file__),
        "script_sha256": hashlib.sha256(
            open(os.path.abspath(__file__), "rb").read()).hexdigest(),
        "python": sys.version,
        "numpy": np.__version__,
        "args": vars(args),
        "runtime_s": runtime_s,
        "constants": {
            "RHO_PRIMARY": RHO_PRIMARY,
            "N_SIMS": N_SIMS,
            "N_SURR": N_SURR,
            "ALPHA": ALPHA,
            "SIGNAL_UV": SIGNAL_UV,
            "CAMERA_NOISE": CAMERA_NOISE,
            "REGION_GRID": REGION_GRID,
            "DETECTORS": DETECTORS,
            "FPR_LO": FPR_LO,
            "FPR_HI": FPR_HI,
            "MARGIN_KEEP": MARGIN_KEEP,
            "MARGIN_DIRECT": MARGIN_DIRECT,
        },
    }
    with open(os.path.join(outdir, "run_meta.json"), "w") as f:
        json.dump(meta, f, indent=2, default=str)

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
    return primary_summary, primary_nulls, decision


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="results/s1b_direct_baseline")
    ap.add_argument("--grid", choices=("primary", "secondary", "all"),
                    default="primary")
    ap.add_argument("--n-sims", type=int, default=N_SIMS)
    ap.add_argument("--n-surr", type=int, default=N_SURR)
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    records = []
    n = 1 if args.pilot else args.n_sims

    if args.grid in ("primary", "all"):
        print("primary quadratic rho=0.9", flush=True)
        records += analyze_cell("quadratic", RHO_PRIMARY, n, args.n_surr,
                                SIGNAL_UV, CAMERA_NOISE)
        print("primary linear rho=0.9", flush=True)
        records += analyze_cell("linear", RHO_PRIMARY, n, args.n_surr,
                                SIGNAL_UV, CAMERA_NOISE)
        print("null rho=0", flush=True)
        records += analyze_cell("linear", 0.0, n, args.n_surr,
                                SIGNAL_UV, CAMERA_NOISE)
        records += analyze_cell("quadratic", 0.0, n, args.n_surr,
                                SIGNAL_UV, CAMERA_NOISE)

    if args.grid in ("secondary", "all"):
        ns = 1 if args.pilot else SECONDARY_N
        print("secondary 20 uV", flush=True)
        records += analyze_cell("quadratic", RHO_PRIMARY, ns, args.n_surr,
                                20.0, CAMERA_NOISE)
        records += analyze_cell("quadratic", 0.0, ns, args.n_surr,
                                20.0, CAMERA_NOISE)
        print("secondary noisy camera", flush=True)
        records += analyze_cell("quadratic", RHO_PRIMARY, ns, args.n_surr,
                                SIGNAL_UV, 0.10)
        records += analyze_cell("quadratic", 0.0, ns, args.n_surr,
                                SIGNAL_UV, 0.10)

    runtime_s = time.time() - t0
    summary, nulls, decision = write_outputs(records, args.outdir, args,
                                             runtime_s)
    print(f"\nwrote {args.outdir} in {runtime_s:.1f} s")
    print(json.dumps({"nulls": nulls, "decision": decision}, indent=2,
                     default=str))


if __name__ == "__main__":
    main()
