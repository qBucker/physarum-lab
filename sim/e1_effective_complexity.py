#!/usr/bin/env python3
"""E1: effective-complexity calibration on synthetic systems.

Purpose
-------
Before fixing a model, measure how many independent modes the observables
actually support, whether the coupling is linear, and whether it is stationary.
This script calibrates the estimators on systems with *known* complexity and
writes a pre-registered protocol for real data.

Pre-registered calibration (do not edit after seeing results)
------------------------------------------------------------
Systems (48 h, 10 s frames, n = 17,280; 20 seeds each):
  s0            : 1 slow mode + electrical noise; linear, stationary; rank 2
  kmode2/4/8    : K slow modes + electrical noise; linear, stationary; rank K+1
  nonlinear     : 1 slow mode; e = rho*s_del + gamma*(s_del^2 - 1) + noise
  nonstationary : 1 slow mode; rho changes at mid-run (0.1 -> 0.4)
Observables: log-envelope-like electrical channel + structural channels,
each with 0.3 observation noise.

Estimators:
  POD/SSA effective rank : participation ratio + surrogate-threshold rank
  BIC model ladder       : ARX(p,q) linear vs quadratic; lowest BIC
  Nonlinearity index     : OOS R^2 gain of quadratic over linear + surrogate p
  Stationarity index     : across-window coupling-coefficient drift / SE
  N_eff                  : T / (2*tau_1/e) of the slowest observable

Outputs (--outdir):
  e1_results.json / e1_results.csv / e1_summary.md
  e1_spectra.png / e1_tests.png / run_meta.json / SHA256SUMS
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time

import numpy as np
from scipy import signal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pipeline import phase_randomize, xcorr_lag

# ---------------------------------------------------------------------------
# Pre-registered constants
# ---------------------------------------------------------------------------
DURATION_H = 48.0
FRAME_DT = 10.0
N = int(DURATION_H * 3600.0 / FRAME_DT)
TAU_S = 7200.0
TAU_E = 1800.0
LAG_S = 600.0
RHO = 0.3
SIGMA_OBS = 0.3
N_SIMS = 20
N_SURR = 30
P_GRID = [1, 2, 4]
Q_GRID = [1, 4, 16, 60]
TRAIN_FRAC = 0.7
N_WINDOWS = 4


def ou(n: int, tau_s: float, rng, sigma: float = 1.0) -> np.ndarray:
    a = np.exp(-FRAME_DT / tau_s)
    b = sigma * np.sqrt(1.0 - a * a)
    return signal.lfilter([b], [1.0, -a], rng.normal(size=n))


def delayed(x: np.ndarray, lag_frames: int) -> np.ndarray:
    if lag_frames <= 0:
        return x.copy()
    y = np.empty_like(x)
    y[:lag_frames] = x[0]
    y[lag_frames:] = x[:-lag_frames]
    return y


def make_system(kind: str, seed: int, K: int = 2, rho: float = RHO):
    rng = np.random.default_rng(seed)
    n = N
    if kind in ("s0", "nonlinear", "nonstationary"):
        s = ou(n, TAU_S, rng)
        s_del = delayed(s, int(round(LAG_S / FRAME_DT)))
        noise = ou(n, TAU_E, rng)
        if kind == "s0":
            e = rho * s_del + np.sqrt(max(0.0, 1.0 - rho * rho)) * noise
            truth = {"kind": kind, "known_rank": 2, "linear": True, "stationary": True}
        elif kind == "nonlinear":
            gamma = 0.3
            e = rho * s_del + gamma * (s_del ** 2 - 1.0) + 0.9 * noise
            truth = {"kind": kind, "known_rank": 2, "linear": False, "stationary": True}
        else:
            rho_t = np.where(np.arange(n) < n // 2, 0.0, 0.6)
            e = rho_t * s_del + np.sqrt(np.maximum(0.0, 1.0 - rho_t ** 2)) * noise
            truth = {"kind": kind, "known_rank": 2, "linear": True, "stationary": False}
        e_obs = e + SIGMA_OBS * rng.normal(size=n)
        s_obs = s + SIGMA_OBS * rng.normal(size=n)
        X = np.column_stack([e_obs, s_obs])
        truth["known_modes"] = 1
        return X, truth

    if kind == "kmode":
        taus = [TAU_S / (2 ** k) for k in range(K)]
        lags = [max(1, int(round((LAG_S / (2 ** k)) / FRAME_DT))) for k in range(K)]
        modes = [ou(n, tau, rng) for tau in taus]
        amp = rho / np.sqrt(K)
        e = np.zeros(n)
        for s_k, lag_k in zip(modes, lags):
            e += amp * delayed(s_k, lag_k)
        noise = ou(n, TAU_E, rng)
        e = e + np.sqrt(max(0.0, 1.0 - rho * rho)) * noise
        e_obs = e + SIGMA_OBS * rng.normal(size=n)
        s_obs = [s_k + SIGMA_OBS * rng.normal(size=n) for s_k in modes]
        X = np.column_stack([e_obs] + s_obs)
        truth = {
            "kind": kind,
            "known_rank": K + 1,
            "known_modes": K,
            "linear": True,
            "stationary": True,
        }
        return X, truth

    raise ValueError(kind)


def standardize(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0, ddof=1)
    return (X - mu) / np.maximum(sd, 1e-30)


def lag_embed(x: np.ndarray, L: int) -> tuple[np.ndarray, np.ndarray]:
    """Delay embedding: rows t = L-1 .. n-1, columns x[t-k]."""
    n = len(x)
    t = np.arange(L - 1, n)
    return x[t[:, None] - np.arange(L)[None, :]], t


def cca_correlations(E: np.ndarray, S: np.ndarray) -> np.ndarray:
    """Canonical correlations between two standardised blocks."""
    E = (E - E.mean(axis=0)) / np.maximum(E.std(axis=0, ddof=1), 1e-30)
    S = (S - S.mean(axis=0)) / np.maximum(S.std(axis=0, ddof=1), 1e-30)
    n = len(E)
    Cxx = E.T @ E / (n - 1)
    Cyy = S.T @ S / (n - 1)
    Cxy = E.T @ S / (n - 1)
    eps = 1e-8
    Cxx += eps * np.eye(E.shape[1])
    Cyy += eps * np.eye(S.shape[1])
    ex, Vx = np.linalg.eigh(Cxx)
    ey, Vy = np.linalg.eigh(Cyy)
    Wx = Vx @ np.diag(ex ** -0.5) @ Vx.T
    Wy = Vy @ np.diag(ey ** -0.5) @ Vy.T
    return np.linalg.svd(Wx @ Cxy @ Wy, compute_uv=False)


def cca_rank(E: np.ndarray, S: np.ndarray, rng, n_surr: int = N_SURR, L: int = 90) -> dict:
    """Shared-mode rank from CCA between electrical delay embedding and structure."""
    Ee, t = lag_embed(E, L)
    Ss = S[t]
    obs = cca_correlations(Ee, Ss)
    null = np.empty((n_surr, len(obs)))
    for k in range(n_surr):
        e_s = phase_randomize(E, rng)
        Ee_s, _ = lag_embed(e_s, L)
        S_s = np.column_stack([phase_randomize(S[:, j], rng) for j in range(S.shape[1])])
        null[k] = cca_correlations(Ee_s, S_s[t])
    q95 = np.quantile(null, 0.95, axis=0)
    rank = int(np.sum(obs > q95))
    return {"cca_rank": rank, "canonical_correlations": [float(x) for x in obs[:12]]}


# ---------------------------------------------------------------------------
# POD / SSA effective rank
# ---------------------------------------------------------------------------
def pod_metrics(X: np.ndarray, rng, n_surr: int = N_SURR) -> dict:
    Xs = standardize(X)
    _, S, _ = np.linalg.svd(Xs, full_matrices=False)
    p = S ** 2 / float(np.sum(S ** 2))
    pr = 1.0 / float(np.sum(p ** 2))
    energy90 = int(np.searchsorted(np.cumsum(p), 0.90) + 1)
    energy95 = int(np.searchsorted(np.cumsum(p), 0.95) + 1)
    null = np.empty((n_surr, len(S)))
    for k in range(n_surr):
        Xn = np.column_stack([phase_randomize(Xs[:, j], rng) for j in range(Xs.shape[1])])
        _, Sn, _ = np.linalg.svd(Xn, full_matrices=False)
        null[k] = Sn
    q95 = np.quantile(null, 0.95, axis=0)
    eff_rank = int(np.sum(S > q95))
    return {
        "pr": float(pr),
        "energy90": energy90,
        "energy95": energy95,
        "eff_rank": eff_rank,
        "singular_values": [float(x) for x in S[:12]],
    }


# ---------------------------------------------------------------------------
# ARX / BIC ladder
# ---------------------------------------------------------------------------
def build_arx(X: np.ndarray, p: int, q: int, s_idx: list[int], quadratic: bool):
    n = X.shape[0]
    L = max(p, q)
    t = np.arange(L, n - 1)
    y = X[t + 1, 0]
    cols = [np.ones(len(t))]
    for k in range(1, p + 1):
        cols.append(X[t + 1 - k, 0])
    for j in s_idx:
        for k in range(q):
            cols.append(X[t - k, j])
    if quadratic:
        for j in s_idx:
            for k in range(q):
                cols.append(X[t - k, j] ** 2)
    Xd = np.column_stack(cols)
    return Xd, y, t


def fit_ols(Xd: np.ndarray, y: np.ndarray, tr: np.ndarray, te: np.ndarray):
    Xtr = Xd[tr]
    coef, *_ = np.linalg.lstsq(Xtr, y[tr], rcond=None)
    pred_tr = Xtr @ coef
    pred_te = Xd[te] @ coef
    sse = float(np.sum((y[tr] - pred_tr) ** 2))
    n = len(tr)
    k = Xd.shape[1]
    bic = n * np.log(max(sse / n, 1e-300)) + k * np.log(n)
    ss_tot = float(np.sum((y[te] - y[te].mean()) ** 2))
    r2 = 1.0 - float(np.sum((y[te] - pred_te) ** 2)) / ss_tot if ss_tot > 0 else float("nan")
    return {"coef": coef, "bic": float(bic), "r2_oos": float(r2), "k": k, "sse": sse}


def split_arrays(n: int, L: int):
    n_train = int(TRAIN_FRAC * n)
    tr = np.arange(0, n_train - L)
    te = np.arange(n_train, n - 1)
    return tr, te


def bic_ladder_2d(X: np.ndarray):
    best = None
    rows = []
    for p in P_GRID:
        for q in Q_GRID:
            for quad in (False, True):
                Xd, y, t = build_arx(X, p, q, [1], quad)
                tr, te = split_arrays(len(t), 0)
                fit = fit_ols(Xd, y, tr, te)
                row = {"p": p, "q": q, "quadratic": quad, "bic": fit["bic"], "r2_oos": fit["r2_oos"]}
                rows.append(row)
                if best is None or fit["bic"] < best["bic"]:
                    best = dict(row)
                    best["coef"] = fit["coef"]
                    best["k"] = fit["k"]
    return best, rows


def nonlinearity_test_2d(X: np.ndarray, rng, n_surr: int = N_SURR, max_lag: int = 90):
    """Static lagged test: e(t) ~ 1 + s(t-k) vs + s(t-k)^2.

    The lag is selected by max |corr|; the surrogate null repeats the whole
    selection.  Do not condition on e's own history: under 10 s oversampling,
    e(t) already contains s(t-600) and the conditional gain is negligible.
    """
    e, s = X[:, 0], X[:, 1]
    n = len(e)

    def gain(e, s):
        lags, r = xcorr_lag(e, s, max_lag)
        k = int(abs(lags[int(np.argmax(np.abs(r)))]))
        t = np.arange(k, n)
        y = e[t]
        sl = s[t - k]
        ntr = int(TRAIN_FRAC * len(y))
        Xl = np.column_stack([np.ones(len(y)), sl])
        Xq = np.column_stack([np.ones(len(y)), sl, sl ** 2])

        def r2(Xd):
            coef, *_ = np.linalg.lstsq(Xd[:ntr], y[:ntr], rcond=None)
            pred = Xd[ntr:] @ coef
            ss_tot = float(np.sum((y[ntr:] - y[ntr:].mean()) ** 2))
            return 1.0 - float(np.sum((y[ntr:] - pred) ** 2)) / ss_tot

        return r2(Xq) - r2(Xl), k

    obs, k_obs = gain(e, s)
    null = np.empty(n_surr)
    for j in range(n_surr):
        s_s = phase_randomize(s, rng)
        null[j] = gain(e, s_s)[0]
    pval = (1.0 + float(np.sum(null >= obs))) / (1.0 + n_surr)
    return {"index": float(obs), "p": float(pval), "lag_frames": int(k_obs)}


def stationarity_test_2d(
    X: np.ndarray, rng, n_windows: int = 4, max_lag: int = 90,
    n_boot: int = 100, block_s: float = 6 * 3600.0,
):
    """Early-vs-late coupling coefficient, calibrated by block bootstrap.

    At the global xcorr lag, fit e(t) ~ 1 + s(t-k) per window.  The statistic
    is mean(last half) - mean(first half); the null is a circular block
    bootstrap of the aligned pair (block = 6 h, shorter than a regime).
    """
    e, s = X[:, 0], X[:, 1]
    n = len(e)
    lags, r = xcorr_lag(e, s, max_lag)
    k = int(abs(lags[int(np.argmax(np.abs(r)))]))
    t = np.arange(k, n)
    y = e[t]
    sl = s[t - k]

    def window_delta(y, sl):
        edges = np.linspace(0, len(y), n_windows + 1, dtype=int)
        bs = []
        for w in range(n_windows):
            yy = y[edges[w]:edges[w + 1]]
            ss = sl[edges[w]:edges[w + 1]]
            Xd = np.column_stack([np.ones(len(yy)), ss])
            coef, *_ = np.linalg.lstsq(Xd, yy, rcond=None)
            bs.append(float(coef[1]))
        bs = np.array(bs)
        half = n_windows // 2
        return float(bs[half:].mean() - bs[:half].mean()), bs

    delta_obs, bs_obs = window_delta(y, sl)
    block_len = max(1, int(block_s / FRAME_DT))
    boots = np.empty(n_boot)
    for b in range(n_boot):
        n_blocks = int(np.ceil(len(y) / block_len))
        starts = rng.integers(0, len(y), size=n_blocks)
        idx = (starts[:, None] + np.arange(block_len)[None, :]) % len(y)
        idx = idx.ravel()[:len(y)]
        boots[b] = window_delta(y[idx], sl[idx])[0]
    sd = float(np.std(boots, ddof=1))
    z = float(abs(delta_obs) / max(sd, 1e-30))
    pval = float((1.0 + np.sum(np.abs(boots - np.median(boots)) >= abs(delta_obs))) / (1.0 + n_boot))
    return {
        "drift_index": z,
        "delta": float(delta_obs),
        "p": pval,
        "coefs": bs_obs.tolist(),
        "boot_sd": sd,
        "lag_frames": int(k),
    }


def neff_from_acf(x: np.ndarray) -> dict:
    """Effective sample size from the integrated autocorrelation time."""
    x = (x - x.mean()) / max(x.std(ddof=1), 1e-30)
    n = len(x)
    X = np.fft.rfft(x, n=2 * n)
    acf = np.fft.irfft(X * np.conj(X))[:n]
    acf = acf / acf[0]
    tau_int = 1.0
    for k in range(1, n):
        if acf[k] < 0.05:
            break
        tau_int += 2.0 * acf[k]
    return {
        "tau_int_samples": float(tau_int),
        "tau_int_s": float(tau_int * FRAME_DT),
        "neff": float(n / tau_int),
    }


def analyze_system(kind: str, seed: int, K: int = 2, n_surr: int = N_SURR):
    X, truth = make_system(kind, seed, K=K)
    Xs = standardize(X)
    rng = np.random.default_rng(seed + 9_000_000)
    pod = pod_metrics(Xs, rng, n_surr=n_surr)
    cca = cca_rank(Xs[:, 0], Xs[:, 1:], rng, n_surr=n_surr)
    acf = neff_from_acf(Xs[:, 1])
    out = {
        "system": kind if kind != "kmode" else f"kmode{K}",
        "seed": int(seed),
        "truth": truth,
        "pod": pod,
        "cca": cca,
        "neff": acf,
        "bic": None,
        "nonlinearity": None,
        "stationarity": None,
    }
    if kind in ("s0", "nonlinear", "nonstationary"):
        best, rows = bic_ladder_2d(Xs)
        out["bic"] = {"best": {k: v for k, v in best.items() if k != "coef"}, "rows": rows}
        out["nonlinearity"] = nonlinearity_test_2d(Xs, rng, n_surr=n_surr)
        out["stationarity"] = stationarity_test_2d(Xs, rng)
    return out


def summarize(records: list[dict]) -> dict:
    systems = sorted({r["system"] for r in records})
    out = {}
    for sysname in systems:
        recs = [r for r in records if r["system"] == sysname]
        def med(key, fn=lambda r: r[key]):
            return float(np.median([fn(r) for r in recs]))
        out[sysname] = {
            "n": len(recs),
            "known_rank": recs[0]["truth"]["known_rank"],
            "known_modes": recs[0]["truth"]["known_modes"],
            "pr": med("pod", lambda r: r["pod"]["pr"]),
            "eff_rank": med("pod", lambda r: r["pod"]["eff_rank"]),
            "cca_rank": med("cca", lambda r: r["cca"]["cca_rank"]),
            "cca_first": med("cca", lambda r: r["cca"]["canonical_correlations"][0]),
            "energy95": med("pod", lambda r: r["pod"]["energy95"]),
            "neff": med("neff", lambda r: r["neff"]["neff"]),
            "bic_p": med("bic", lambda r: r["bic"]["best"]["p"]) if recs[0]["bic"] else None,
            "bic_q": med("bic", lambda r: r["bic"]["best"]["q"]) if recs[0]["bic"] else None,
            "bic_quadratic": (
                float(np.mean([r["bic"]["best"]["quadratic"] for r in recs]))
                if recs[0]["bic"]
                else None
            ),
            "nonlinearity_index": (
                med("nonlinearity", lambda r: r["nonlinearity"]["index"])
                if recs[0]["nonlinearity"]
                else None
            ),
            "nonlinearity_p": (
                med("nonlinearity", lambda r: r["nonlinearity"]["p"])
                if recs[0]["nonlinearity"]
                else None
            ),
            "drift_index": (
                med("stationarity", lambda r: r["stationarity"]["drift_index"])
                if recs[0]["stationarity"]
                else None
            ),
            "drift_p": (
                med("stationarity", lambda r: r["stationarity"]["p"])
                if recs[0]["stationarity"]
                else None
            ),
            "nonlinearity_power": (
                float(np.mean([r["nonlinearity"]["p"] < 0.05 for r in recs]))
                if recs[0]["nonlinearity"]
                else None
            ),
            "drift_power": (
                float(np.mean([r["stationarity"]["p"] < 0.05 for r in recs]))
                if recs[0]["stationarity"]
                else None
            ),
        }
    return out


def write_outputs(records, summary, outdir, args):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "e1_results.json"), "w") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2)

    fields = ["system", "seed", "known_rank", "known_modes", "pr", "eff_rank",
              "cca_rank", "cca_first", "energy95", "neff",
              "bic_p", "bic_q", "bic_quadratic", "nonlinearity_index", "nonlinearity_p",
              "drift_index", "drift_p"]
    with open(os.path.join(outdir, "e1_results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            row = {
                "system": r["system"],
                "seed": r["seed"],
                "known_rank": r["truth"]["known_rank"],
                "known_modes": r["truth"]["known_modes"],
                "pr": r["pod"]["pr"],
                "eff_rank": r["pod"]["eff_rank"],
                "cca_rank": r["cca"]["cca_rank"],
                "cca_first": r["cca"]["canonical_correlations"][0],
                "energy95": r["pod"]["energy95"],
                "neff": r["neff"]["neff"],
                "bic_p": r["bic"]["best"]["p"] if r["bic"] else "",
                "bic_q": r["bic"]["best"]["q"] if r["bic"] else "",
                "bic_quadratic": r["bic"]["best"]["quadratic"] if r["bic"] else "",
                "nonlinearity_index": r["nonlinearity"]["index"] if r["nonlinearity"] else "",
                "nonlinearity_p": r["nonlinearity"]["p"] if r["nonlinearity"] else "",
                "drift_index": r["stationarity"]["drift_index"] if r["stationarity"] else "",
                "drift_p": r["stationarity"]["p"] if r["stationarity"] else "",
            }
            w.writerow(row)

    # Figure 1: normalized singular-value spectra.
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=150)
    for sysname in ["s0", "kmode2", "kmode4", "kmode8"]:
        recs = [r for r in records if r["system"] == sysname]
        if not recs:
            continue
        sv = np.median(np.array([r["pod"]["singular_values"] for r in recs]), axis=0)
        p = sv ** 2 / np.sum(sv ** 2)
        ax.plot(np.arange(1, len(p) + 1), p, "o-", label=sysname)
    ax.set_yscale("log")
    ax.set_xlabel("POD component")
    ax.set_ylabel("fraction of variance")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title("POD spectra: known rank 2 / 3 / 5 / 9")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "e1_spectra.png"))

    # Figure 2: linearity and drift tests.
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6), dpi=150)
    for ax, key, title in [
        (axes[0], "nonlinearity", "Nonlinearity index (OOS R2 gain)"),
        (axes[1], "stationarity", "Coupling-coefficient drift / SE"),
    ]:
        labels, vals = [], []
        for sysname in ["s0", "nonlinear", "nonstationary"]:
            recs = [r for r in records if r["system"] == sysname and r[key] is not None]
            if not recs:
                continue
            labels.append(sysname)
            vals.append([r[key]["index"] if key == "nonlinearity" else r[key]["drift_index"] for r in recs])
        ax.boxplot(vals)
        ax.set_xticks(range(1, len(labels) + 1))
        ax.set_xticklabels(labels)
        ax.set_title(title, fontsize=9)
        ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "e1_tests.png"))

    with open(os.path.join(outdir, "e1_summary.md"), "w") as f:
        f.write("# E1 — effective-complexity calibration (synthetic, known truth)\n\n")
        f.write("Evidence label: **computed (model-internal)**. 48 h, 10 s frames, "
                "20 seeds/system; `known_rank` = structure modes + one electrical noise mode.\n\n")
        f.write("| system | known modes | known rank | POD PR | CCA rank | energy 95% | "
                "N_eff | BIC p/q/quad | lin index | lin p | lin power | drift | drift p | "
                "drift power |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|\n")
        for sysname, s in summary.items():
            bic = "" if s["bic_p"] is None else f"{s['bic_p']:.0f}/{s['bic_q']:.0f}/{s['bic_quadratic']:.2f}"
            lin_idx = "" if s["nonlinearity_index"] is None else f"{s['nonlinearity_index']:.4f}"
            lin_p = "" if s["nonlinearity_p"] is None else f"{s['nonlinearity_p']:.3f}"
            lin_pow = "" if s.get("nonlinearity_power") is None else f"{s['nonlinearity_power']:.2f}"
            drift = "" if s["drift_index"] is None else f"{s['drift_index']:.2f}"
            dp = "" if s.get("drift_p") is None else f"{s['drift_p']:.3f}"
            dpow = "" if s.get("drift_power") is None else f"{s['drift_power']:.2f}"
            f.write(
                f"| {sysname} | {s['known_modes']} | {s['known_rank']} | {s['pr']:.2f} | "
                f"{s['cca_rank']:.0f} | {s['energy95']:.0f} | {s['neff']:.1f} | {bic} | "
                f"{lin_idx} | {lin_p} | {lin_pow} | {drift} | {dp} | {dpow} |\n"
            )
        f.write("\nPre-registered: alpha = 0.05; 30 phase-randomised surrogates; "
                "PR = participation ratio (total variance dimension); CCA rank = shared "
                "modes from one electrical channel (conservative); lin/drift power = "
                "fraction of 20 seeds with p < 0.05; BIC q = 1 is an oversampling "
                "artifact, not a lag estimate; BIC p in {1,2,4}, q in {1,4,16,60}.\n")

    meta = {
        "script": os.path.basename(__file__),
        "python": os.sys.version,
        "numpy": np.__version__,
        "args": vars(args),
        "constants": {
            "DURATION_H": DURATION_H,
            "FRAME_DT": FRAME_DT,
            "N": N,
            "TAU_S": TAU_S,
            "TAU_E": TAU_E,
            "LAG_S": LAG_S,
            "RHO": RHO,
            "SIGMA_OBS": SIGMA_OBS,
            "N_SIMS": N_SIMS,
            "N_SURR": N_SURR,
            "P_GRID": P_GRID,
            "Q_GRID": Q_GRID,
            "TRAIN_FRAC": TRAIN_FRAC,
            "N_WINDOWS": N_WINDOWS,
        },
    }
    with open(os.path.join(outdir, "run_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

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
    ap.add_argument("--outdir", default="results/e1_effective_complexity")
    ap.add_argument("--n-sims", type=int, default=N_SIMS)
    ap.add_argument("--n-surr", type=int, default=N_SURR)
    ap.add_argument("--systems", type=str, default="s0,kmode2,kmode4,kmode8,nonlinear,nonstationary")
    args = ap.parse_args()

    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    t0 = time.time()
    records = []
    for sys_idx, sysname in enumerate(systems):
        kind = "kmode" if sysname.startswith("kmode") else sysname
        K = int(sysname.replace("kmode", "")) if kind == "kmode" else 2
        for k in range(args.n_sims):
            seed = 3_000_000 + sys_idx * 10_000 + k
            rec = analyze_system(kind, seed, K=K, n_surr=args.n_surr)
            rec["system"] = sysname
            records.append(rec)
            print(
                f"{sysname} seed={seed} PR={rec['pod']['pr']:.2f} "
                f"rank={rec['pod']['eff_rank']} cca={rec['cca']['cca_rank']} "
                f"N_eff={rec['neff']['neff']:.1f} "
                f"bic={rec['bic']['best']['p'] if rec['bic'] else '-'}/"
                f"{rec['bic']['best']['q'] if rec['bic'] else '-'}/"
                f"{rec['bic']['best']['quadratic'] if rec['bic'] else '-'} "
                f"lin={rec['nonlinearity']['index'] if rec['nonlinearity'] else '-'} "
                f"drift={rec['stationarity']['drift_index'] if rec['stationarity'] else '-'}",
                flush=True,
            )

    summary = summarize(records)
    write_outputs(records, summary, args.outdir, args)
    print(f"\nwrote {args.outdir} in {time.time() - t0:.1f} s")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
