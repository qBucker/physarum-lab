#!/usr/bin/env python3
"""S1: high-dimensional / nonlinear network testbed for the latent pipeline.

Question
--------
R1 (2026-11-14) showed that on the 2-D S0 truth the latent pipeline
(POD -> delay embedding -> DMDc/ARX) has no gain over direct lagged
cross-correlation at realistic coupling.  R1 did not test the two steps that
need a high-dimensional, nonlinear truth: geometric POD and a nonlinear
latent library.  S1 supplies both:

  * truth: a stationary stochastic Tero-Kobayashi network on a 12-node /
    ~24-edge planar graph.  Edge conductances D_e(t) = exp(x_e) follow a
    log-homeostatic flow-adaptation process (see "Truth model" below), a
    genuinely high-dimensional, nonlinear, stationary structural state.
  * camera: a 24 x 20 pixel image of tube thickness (linear in D), then
    training-segment POD.  The camera is a linear noisy projection of D.
  * electrodes: 8/16/32 electrodes with a Gaussian lead-field mixing all
    edge sources; the measured potential is exp(0.5 z) times a 0.03 Hz
    carrier, passed through the S0 instrument model.
  * coupling: electrical edge source x_e(t) = D_e(t-lag) ("linear") or
    x_e(t) = (D_e(t-lag) - mean)^2 ("quadratic").  The quadratic cell is
    deliberately invisible to linear statistics but recoverable by a
    quadratic latent library.

Detectors (pre-registered)
  D1   scalar direct: max |r| between electrical PC1 and geometry POD1 over
       +/-1800 s, phase-randomised surrogate.
  D2   multivariate direct: max over lags of the first canonical correlation
       between the q electrical PCs and the r geometry POD scores, common-
       phase surrogate.
  D1f  D1 at the pre-registered lag only (no scan).
  D2f  D2 at the pre-registered lag only (no scan).
  L1   latent linear, partial delayed gain: E(t) ~ [G(t), G(t-600)] vs
       E(t) ~ G(t); statistic = full-sample R^2 gain of the delayed block,
       common-phase surrogate.  Reverse (G from E) is run symmetrically.
  L2   latent quadratic, delayed-quadratic gain: E(t) ~ [G(t), Q(G(t)),
       G(t-600)] vs the same plus Q(G(t-600)); statistic = R^2 gain of the
       delayed quadratic block.  This isolates the nonlinear delayed
       information while controlling the instantaneous linear/quadratic
       relation.  Reverse symmetric.

Truth model (a testbed device, not a biological claim)
  d log D_e = [-(log D_e - log D0) + alpha (q_e^mu/(1+q_e^mu) - 1/2)] dt/tau
              + sigma sqrt(dt/tau) dW,
  with q_e the edge flow normalised by its initial median, tau = 7200 s,
  mu = 1.5, alpha = 0.5, sigma = 0.3, log D0 = log 0.5, and source
  pressures 1 + 0.3 * OU(tau=7200 s).  The log-homeostatic term keeps the
  structure stationary and bounded; without it the classical TK rule prunes
  ~1/3 of the edges to the floor and invalidates train/test comparisons.

Pre-registered design (do not edit after seeing results)
-------------------------------------------------------
Primary grid
  coupling     : linear, quadratic
  rho          : 0.0, 0.5, 0.7, 0.9
  n_sims       : 30 per cell (240 runs)
  electrodes   : K = 16
  duration     : 56 h simulated, first 8 h discarded, 48 h analysed
  frames       : 10 s; electrical sampled at 1 Hz
  lag          : 600 s (structure leads electrical activity)
  signal       : 100 uV carrier (instrument noise subdominant; S0 owns the
                 20 uV detectability question), 10 uV in-band flicker,
                 1 mV/h drift, 10 kOhm source, ADC 1 SPS PGA 8
  camera       : 24 x 20 pixels, line width 1.2 mm, pixel noise 0.03 in
                 per-edge training-sd units (SNR ~10:1)
  background   : tau_e = 1800 s, common + independent components
  graph        : per-seed Delaunay graph, 12 nodes in 40 x 30 mm, min
                 separation 5 mm, edges <= 25 mm plus MST edges;
                 sources = 2 lowest-y nodes, sinks = 2 highest-y nodes
  POD          : training-segment PCA (70/30 split), retain
                 r = min(r90, 8) modes, r90 = 90% variance
  electrical   : q = 3 PCs of the log-envelope (training-segment basis)
  ridge        : lambda = 1e-3 * trace(X'X)/d
  surrogates   : 50 per test, common-phase randomisation across modes
  alpha        : 0.05
Secondary grid (pre-registered)
  coupling     : quadratic
  K            : 8, 32
  rho          : 0.0, 0.7
  n_sims       : 20 per cell (80 runs)
Positive control (diagnostic, not part of the decision)
  clean = true: no flicker, drift, background or camera noise; rho = 1
  both couplings, n = 10.  Expected: linear cell -> L1 detects; quadratic
  cell -> L1 fails, L2 detects.

Why rho >= 0.5 (design-stage correction, documented in the summary)
  The pilot showed that at rho = 0.2/0.3 the null R^2 among slow modes
  (~0.15) exceeds the expected structural signal (~0.07); those cells are
  uninformative by construction.  S1 therefore maps the operating range
  rho = 0.5-0.9.  This is a power correction made before the full run, not
  a result-driven grid change.

Matched-FPR rule
  Pooled rho=0 cells (60 runs primary) give the empirical FPR of each
  detector.  If a detector's pooled FPR is outside [0.02, 0.10], power
  comparisons for that detector use the empirical 95th percentile of its
  rho=0 statistics as the threshold ("threshold matching").  The summary
  reports both nominal and matched numbers.

Decision rule (pre-registered)
  Informative cell: the highest rho in {0.5, 0.7, 0.9} at which at least
  one main detector reaches power >= 0.5 in the quadratic-coupling cell.
  If none, the verdict is UNDETERMINED (testbed underpowered), not a kill.
  At the informative rho:
    - the latent pipeline earns its keep only if
      max(L1, L2) >= max(D1, D2) + 0.20 in the quadratic cell,
      with forward/reverse direction correct in >=80% of detected runs;
    - L2 specificity: if L2 also detects the linear-coupling cell at the
      same rho with power >= 0.20, the nonlinear layer is labelled
      "not specific" and cannot support a keep verdict on its own;
    - the linear cell is a control: L1 must not fall more than 0.20 below
      the best direct detector.
  Otherwise the latent pipeline is downgraded per the R1 kill criterion.

Outputs (in --outdir)
  s1_results.json / s1_results.csv
  s1_summary.md
  s1_power.png
  run_meta.json
  SHA256SUMS
  exemplar_<coupling>_rho09.npz (one seed per coupling)

Reproduce
  cd physarum-lab/sim
  OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 \
      python3 s1_network_testbed.py --grid all --outdir results/s1_network

Pilot fixes already applied (before the full run)
  * ARPACK truncated POD instead of multithreaded LAPACK eigh (pathological
    on this WSL host).
  * Camera noise 0.3 -> 0.03 (the former made POD noise-dominated).
  * Classical TK -> log-homeostatic TK (the former pruned edges and broke
    train/test exchangeability).
  * Incremental prediction from full delay embeddings -> partial delayed
    gain (the former overfit and was absorbed by E's own history).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time

# Set BLAS threads before importing numpy.  On this WSL host the
# multithreaded symmetric eigensolver is pathologically slow; all POD work
# uses truncated ARPACK instead, and 4 threads keep dense GEMM fast.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np
from scipy import signal
from scipy.sparse.linalg import LinearOperator, eigsh
from scipy.spatial import Delaunay
from scipy.sparse.csgraph import minimum_spanning_tree

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from instrument import ADCModel, ElectrodeModel, measure
from pipeline import phase_randomize, xcorr_lag

# ---------------------------------------------------------------------------
# Pre-registered constants
# ---------------------------------------------------------------------------
GRAPH_NODES = 12
DOMAIN_MM = (40.0, 30.0)
MIN_SEP_MM = 5.0
MAX_EDGE_MM = 25.0

TOTAL_H = 56.0
BURN_H = 8.0
DURATION_H = 48.0
FRAME_DT = 10.0
FS = 1.0
LAG_S = 600.0
TAU_D = 7200.0
TK_MU = 1.5
TK_ALPHA = 0.5
SIGMA_LOG = 0.3
LOG_D0 = 0.5
SOURCE_SIGMA = 0.3

CAMERA_PIX = (24, 20)
CAMERA_WIDTH_MM = 1.2
CAMERA_NOISE = 0.03
CAMERA_R_MAX = 8
CAMERA_VAR_RULE = 0.90

ELEC_K = 16
ELEC_SIGMA_MM = 6.0
SIGNAL_UV = 100.0
FLICKER_UV = 10.0
DRIFT_MV_H = 1.0
Z_SOURCE_OHM = 10e3
ELEC_Q = 3

TRAIN_FRAC = 0.7
RIDGE_FRAC = 1e-3
ALPHA = 0.05
LAG_TOL_S = 120.0
MAX_LAG_FRAMES = 180

PRIMARY_COUPLINGS = ("linear", "quadratic")
PRIMARY_RHO = (0.0, 0.5, 0.7, 0.9)
PRIMARY_N = 30
N_SURR = 50

SECONDARY_K = (8, 32)
SECONDARY_RHO = (0.0, 0.7)
SECONDARY_N = 20

CLEAN_N = 10
CLEAN_RHO = 1.0

FPR_LO = 0.02
FPR_HI = 0.10
POWER_MARGIN = 0.20
INFORMATIVE_POWER = 0.50
DIRECTION_MIN = 0.80
SPECIFICITY_MAX = 0.20

MAIN_DETECTORS = ("d1", "d2", "l1", "l2")
ALL_DETECTORS = ("d1", "d2", "d1f", "d2f", "l1", "l2")


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
def seed_for(block: str, coupling: str, k: int, sim: int, rho: float) -> int:
    base = {"primary": 10_000_000, "secondary": 20_000_000,
            "positive": 30_000_000}[block]
    ci = PRIMARY_COUPLINGS.index(coupling) if coupling in PRIMARY_COUPLINGS else 0
    ki = {8: 0, 16: 1, 32: 2}[k]
    ri = {0.0: 0, 0.5: 1, 0.7: 2, 0.9: 3, 1.0: 4}[float(rho)]
    return base + ci * 1_000_000 + ki * 100_000 + ri * 20_000 + sim


# ---------------------------------------------------------------------------
# Graph and stationary TK truth
# ---------------------------------------------------------------------------
def make_graph(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    width, height = DOMAIN_MM
    pts: list[np.ndarray] = []
    while len(pts) < GRAPH_NODES:
        p = rng.uniform([0.0, 0.0], [width, height])
        if all(np.hypot(*(p - q)) > MIN_SEP_MM for q in pts):
            pts.append(p)
    pts = np.asarray(pts)

    tri = Delaunay(pts)
    edges: set[tuple[int, int]] = set()
    for simplex in tri.simplices:
        for a, b in ((0, 1), (1, 2), (0, 2)):
            i, j = sorted((int(simplex[a]), int(simplex[b])))
            edges.add((i, j))
    edges = {e for e in edges if np.hypot(*(pts[e[0]] - pts[e[1]])) <= MAX_EDGE_MM}

    dmat = np.hypot(pts[:, None, 0] - pts[None, :, 0],
                    pts[:, None, 1] - pts[None, :, 1])
    mst = minimum_spanning_tree(dmat + 1e-9).toarray()
    for i in range(GRAPH_NODES):
        for j in range(GRAPH_NODES):
            if mst[i, j] > 0:
                edges.add((min(i, j), max(i, j)))

    edges = sorted(edges)
    n_edges = len(edges)
    rows = np.array([e[0] for e in edges], dtype=int)
    cols = np.array([e[1] for e in edges], dtype=int)
    B = np.zeros((GRAPH_NODES, n_edges))
    B[rows, np.arange(n_edges)] = 1.0
    B[cols, np.arange(n_edges)] = -1.0

    order = np.argsort(pts[:, 1])
    sinks = np.sort(order[-2:])
    sources = np.sort(order[:2])
    free = np.setdiff1d(np.arange(GRAPH_NODES), np.r_[sources, sinks])

    return {
        "pts": pts,
        "edges": edges,
        "B": B,
        "sources": sources,
        "sinks": sinks,
        "free": free,
    }


def solve_pressure(D: np.ndarray, graph: dict, ps: np.ndarray) -> tuple:
    B = graph["B"]
    src, snk, free = graph["sources"], graph["sinks"], graph["free"]
    L = (B * D) @ B.T
    p = np.zeros(GRAPH_NODES)
    p[src] = ps
    p[snk] = 0.0
    bnd = np.r_[src, snk]
    p[free] = np.linalg.solve(
        L[np.ix_(free, free)],
        -L[np.ix_(free, bnd)] @ p[bnd],
    )
    Q = D * (B.T @ p)
    return p, Q


def simulate_network(seed: int) -> dict:
    """Stationary log-homeostatic TK testbed; returns analysed-window D, Q."""
    graph = make_graph(seed)
    rng = np.random.default_rng(seed + 1)
    m = len(graph["edges"])
    log_d0 = np.log(LOG_D0)
    x = np.full(m, log_d0) + 0.3 * rng.normal(size=m)
    D = np.exp(x)

    _, Q = solve_pressure(D, graph, np.ones(len(graph["sources"])))
    Q0 = float(np.median(np.abs(Q)))
    if Q0 <= 0:
        Q0 = 1.0

    n_total = int(TOTAL_H * 3600.0 / FRAME_DT)
    z = np.zeros(len(graph["sources"]))
    a = np.exp(-FRAME_DT / TAU_D)
    b = np.sqrt(1.0 - a * a)
    D_hist = np.empty((m, n_total), dtype=np.float32)
    Q_hist = np.empty((m, n_total), dtype=np.float32)

    for k in range(n_total):
        z = a * z + b * rng.normal(size=len(z))
        ps = 1.0 + SOURCE_SIGMA * z
        _, Q = solve_pressure(D, graph, ps)
        q = np.abs(Q / Q0)
        feedback = q ** TK_MU / (1.0 + q ** TK_MU) - 0.5
        x = x + (-(x - log_d0) + TK_ALPHA * feedback) * (FRAME_DT / TAU_D)
        x += SIGMA_LOG * np.sqrt(FRAME_DT / TAU_D) * rng.normal(size=m)
        x = np.clip(x, -8.0, 2.0)
        D = np.exp(x)
        D_hist[:, k] = D
        Q_hist[:, k] = Q / Q0

    i0 = int(round(BURN_H * 3600.0 / FRAME_DT))
    return {
        "graph": graph,
        "D": D_hist[:, i0:],
        "Q": Q_hist[:, i0:],
    }


# ---------------------------------------------------------------------------
# Camera observation and POD
# ---------------------------------------------------------------------------
def camera_weights(pts: np.ndarray, edges: list[tuple[int, int]]) -> np.ndarray:
    height, width = CAMERA_PIX
    xs = (np.arange(width) + 0.5) * DOMAIN_MM[0] / width
    ys = (np.arange(height) + 0.5) * DOMAIN_MM[1] / height
    XX, YY = np.meshgrid(xs, ys)
    pixels = np.column_stack([XX.ravel(), YY.ravel()])
    W = np.zeros((len(pixels), len(edges)))
    for e, (i, j) in enumerate(edges):
        A, Bp = pts[i], pts[j]
        AB = Bp - A
        L2 = float(AB @ AB)
        s = np.clip(((pixels - A) @ AB) / max(L2, 1e-12), 0.0, 1.0)
        proj = A + s[:, None] * AB
        W[:, e] = np.exp(-np.sum((pixels - proj) ** 2, axis=1)
                         / (2.0 * CAMERA_WIDTH_MM ** 2))
    W /= np.maximum(W.sum(axis=0, keepdims=True), 1e-30)
    return W


def pod_scores(image: np.ndarray, train_frac: float = TRAIN_FRAC) -> dict:
    """Training-segment PCA of the camera frames (ARPACK, not LAPACK eigh)."""
    X = np.asarray(image, dtype=float)
    n, p = X.shape
    ntr = int(train_frac * n)
    Xtr = X[:ntr]
    mu = Xtr.mean(axis=0)
    Xtr = Xtr - mu
    total_var = float(np.sum(Xtr.var(axis=0, ddof=1)))
    if total_var <= 0:
        raise RuntimeError("camera signal has zero variance")

    def matvec(v):
        return Xtr.T @ (Xtr @ v)

    op = LinearOperator((p, p), matvec=matvec, dtype=float)
    k = int(min(CAMERA_R_MAX + 2, p - 1))
    try:
        ev, V = eigsh(op, k=k, which="LM")
    except Exception:
        _, S, Vt = np.linalg.svd(Xtr, full_matrices=False)
        ev = S[:k] ** 2 / max(ntr - 1, 1)
        V = Vt[:k].T
    order = np.argsort(ev)[::-1]
    ev = np.maximum(ev[order], 0.0)
    V = V[:, order]
    # The ARPACK operator is the scatter matrix X'X, not the covariance.
    frac = (ev / max(ntr - 1, 1)) / max(total_var, 1e-30)
    r90 = int(np.searchsorted(np.cumsum(frac), CAMERA_VAR_RULE) + 1)
    r90 = min(r90, p)
    r = int(min(r90, CAMERA_R_MAX))

    Xc = X - mu
    G = Xc @ V[:, :r]
    mu_g = G[:ntr].mean(axis=0)
    sd_g = np.maximum(G[:ntr].std(axis=0, ddof=1), 1e-30)
    G = (G - mu_g) / sd_g
    return {
        "G": G,
        "basis": V[:, :r],
        "mean": mu,
        "r90": r90,
        "r": r,
        "var_frac_top": frac[:12].tolist(),
        "total_var": total_var,
    }


# ---------------------------------------------------------------------------
# Electrical observation
# ---------------------------------------------------------------------------
def electrode_positions(k: int) -> np.ndarray:
    if k == 8:
        xs = np.linspace(5.0, 35.0, 4)
        ys = np.linspace(7.5, 22.5, 2)
    elif k == 16:
        xs = np.linspace(5.0, 35.0, 4)
        ys = np.linspace(5.0, 26.0, 4)
    elif k == 32:
        xs = np.linspace(3.5, 36.5, 8)
        ys = np.linspace(5.0, 26.0, 4)
    else:
        raise ValueError(f"unsupported electrode count: {k}")
    return np.array([[x, y] for y in ys for x in xs], dtype=float)


def lead_field(pts: np.ndarray, edges: list[tuple[int, int]], k: int) -> np.ndarray:
    mids = pts[np.array(edges)].mean(axis=1)
    electrodes = electrode_positions(k)
    d2 = (electrodes[:, None, 0] - mids[None, :, 0]) ** 2 + \
         (electrodes[:, None, 1] - mids[None, :, 1]) ** 2
    A = np.exp(-d2 / (2.0 * ELEC_SIGMA_MM ** 2))
    A /= np.maximum(np.linalg.norm(A, axis=1, keepdims=True), 1e-30)
    return A


def ou_series(n: int, tau_s: float, rng) -> np.ndarray:
    a = np.exp(-FRAME_DT / tau_s)
    b = np.sqrt(1.0 - a * a)
    return signal.lfilter([b], [1.0, -a], rng.normal(size=n))


def electrical_observation(
    seed: int,
    graph: dict,
    D: np.ndarray,
    coupling: str,
    rho: float,
    k: int,
    clean: bool = False,
) -> dict:
    rng = np.random.default_rng(seed + 2)
    m, n = D.shape
    t_frames = np.arange(n) * FRAME_DT

    A = lead_field(graph["pts"], graph["edges"], k)

    if coupling == "linear":
        x = D.astype(float).copy()
    elif coupling == "quadratic":
        x = (D.astype(float) - D.mean(axis=1, keepdims=True)) ** 2
    else:
        raise ValueError(coupling)
    x = x / np.maximum(x.std(axis=1, ddof=1, keepdims=True), 1e-30)

    lag = int(round(LAG_S / FRAME_DT))
    xd = np.empty_like(x)
    xd[:, lag:] = x[:, :-lag]
    xd[:, :lag] = x[:, :1]

    s = A @ xd
    s = s / max(float(s.std()), 1e-30)

    if clean:
        b = np.zeros((k, n))
    else:
        common = ou_series(n, 1800.0, rng)
        ind = np.array([ou_series(n, 1800.0, rng) for _ in range(k)])
        b = np.sqrt(0.5) * common[None, :] + np.sqrt(0.5) * ind
        b = b / np.maximum(b.std(axis=1, ddof=1, keepdims=True), 1e-30)

    z = rho * s + np.sqrt(max(0.0, 1.0 - rho * rho)) * b
    z = z / np.maximum(z.std(axis=1, ddof=1, keepdims=True), 1e-30)

    t1 = np.arange(int(n * FRAME_DT), dtype=float)
    z1 = np.empty((k, len(t1)))
    for c in range(k):
        z1[c] = np.interp(t1, t_frames, z[c])
    carrier = np.empty((k, len(t1)))
    phases = rng.uniform(0.0, 2.0 * np.pi, k)
    for c in range(k):
        carrier[c] = (SIGNAL_UV / 1e3) * np.exp(0.5 * z1[c]) * \
            np.cos(2.0 * np.pi * 0.03 * t1 + phases[c])

    if clean:
        # Consistent with the non-clean path, which analyses log(envelope).
        env1 = 0.5 * z1
    else:
        elec = ElectrodeModel(
            z_source_ohm=Z_SOURCE_OHM,
            drift_mv_per_h=DRIFT_MV_H,
            flicker_uv_rms=FLICKER_UV,
        )
        adc = ADCModel(fs=FS, pga=8.0)
        env1 = np.empty_like(carrier)
        sos = signal.butter(4, [0.02, 0.05], btype="bandpass", fs=FS,
                            output="sos")
        for c in range(k):
            eo = measure(carrier[c], t1, elec, adc, rng)
            env1[c] = np.abs(signal.hilbert(signal.sosfiltfilt(sos, eo)))
        env1 = np.log(np.maximum(env1, 1e-9))

    env = np.empty((k, n))
    for c in range(k):
        env[c] = np.interp(t_frames, t1, env1[c])

    ntr = int(TRAIN_FRAC * n)
    mu = env[:, :ntr].mean(axis=1, keepdims=True)
    sd = env[:, :ntr].std(axis=1, ddof=1, keepdims=True)
    env_z = (env - mu) / np.maximum(sd, 1e-30)
    X = env_z.T
    C = X[:ntr].T @ X[:ntr] / max(ntr - 1, 1)
    ev, V = np.linalg.eigh(C)
    order = np.argsort(ev)[::-1]
    ev = ev[order]
    V = V[:, order]
    q = int(min(ELEC_Q, k))
    Ee = X @ V[:, :q]
    mu_e = Ee[:ntr].mean(axis=0)
    sd_e = np.maximum(Ee[:ntr].std(axis=0, ddof=1), 1e-30)
    Ee = (Ee - mu_e) / sd_e

    return {
        "Ee": Ee,
        "env_z": env_z,
        "elec_var_top": ev[:8].tolist(),
        "q": q,
    }


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------
def common_phase_randomize(M: np.ndarray, rng) -> np.ndarray:
    """One random all-pass phase filter applied to every column of M."""
    M = np.asarray(M, dtype=float)
    n = len(M)
    F = np.fft.rfft(M, axis=0)
    ph = rng.uniform(0.0, 2.0 * np.pi, len(F))
    ph[0] = 0.0
    if n % 2 == 0:
        ph[-1] = 0.0
    return np.fft.irfft(F * np.exp(1j * ph)[:, None], n=n, axis=0)


def detect_scalar_direct(e: np.ndarray, g: np.ndarray, n_surr: int,
                         rng) -> dict:
    lags, r = xcorr_lag(e, g, MAX_LAG_FRAMES)
    idx = int(np.argmax(np.abs(r)))
    obs = float(abs(r[idx]))
    lag_s = float(lags[idx] * FRAME_DT)
    null = np.empty(n_surr)
    for k in range(n_surr):
        gs = phase_randomize(g, rng)
        _, r2 = xcorr_lag(e, gs, MAX_LAG_FRAMES)
        null[k] = float(np.max(np.abs(r2)))
    p = (1.0 + float(np.sum(null >= obs))) / (1.0 + n_surr)
    return {
        "stat": obs,
        "p": p,
        "lag_s": lag_s,
        "lag_abs_err_s": abs(lag_s - LAG_S),
        "direction": 1 if lag_s > 0 else -1,
    }


def detect_scalar_fixed(e: np.ndarray, g: np.ndarray, n_surr: int,
                        rng) -> dict:
    k = int(round(LAG_S / FRAME_DT))
    n = len(e)
    ec = (e - e.mean()) / max(e.std(ddof=1), 1e-30)
    gc = (g - g.mean()) / max(g.std(ddof=1), 1e-30)
    obs = float(abs(np.mean(ec[k:] * gc[: n - k])))
    null = np.empty(n_surr)
    for j in range(n_surr):
        gs = phase_randomize(g, rng)
        gs = (gs - gs.mean()) / max(gs.std(ddof=1), 1e-30)
        null[j] = float(abs(np.mean(ec[k:] * gs[: n - k])))
    p = (1.0 + float(np.sum(null >= obs))) / (1.0 + n_surr)
    return {
        "stat": obs,
        "p": p,
        "lag_s": LAG_S,
        "lag_abs_err_s": 0.0,
        "direction": 1,
    }


def _whitener(C: np.ndarray) -> np.ndarray:
    ev, V = np.linalg.eigh(C)
    ev = np.maximum(ev, 1e-12)
    return V @ np.diag(ev ** -0.5) @ V.T


def _cca_at(E: np.ndarray, G: np.ndarray, lags: np.ndarray) -> np.ndarray:
    n = len(E)
    q, r = E.shape[1], G.shape[1]
    Cxx = E.T @ E / (n - 1)
    Cyy = G.T @ G / (n - 1)
    Wx = _whitener(Cxx)
    Wy = _whitener(Cyy)
    vals = np.empty(len(lags))
    for idx, k in enumerate(lags):
        if k >= 0:
            A, B = E[k:], G[: n - k]
        else:
            A, B = E[: n + k], G[-k:]
        Cxy = A.T @ B / len(A)
        vals[idx] = np.linalg.svd(Wx @ Cxy @ Wy, compute_uv=False)[0]
    return vals


def detect_cca_at_lag(E: np.ndarray, G: np.ndarray, n_surr: int,
                      rng) -> dict:
    """Max canonical correlation over lags; positive lag = E lags G."""
    n = len(E)
    E = (E - E.mean(axis=0)) / np.maximum(E.std(axis=0, ddof=1), 1e-30)
    G = (G - G.mean(axis=0)) / np.maximum(G.std(axis=0, ddof=1), 1e-30)
    lags = np.arange(-MAX_LAG_FRAMES, MAX_LAG_FRAMES + 1)
    vals = _cca_at(E, G, lags)
    idx = int(np.argmax(vals))
    obs = float(vals[idx])
    lag_s = float(lags[idx] * FRAME_DT)
    null = np.empty(n_surr)
    for k in range(n_surr):
        Gs = common_phase_randomize(G, rng)
        Gs = (Gs - Gs.mean(axis=0)) / np.maximum(
            Gs.std(axis=0, ddof=1), 1e-30)
        null[k] = float(np.max(_cca_at(E, Gs, lags)))
    p = (1.0 + float(np.sum(null >= obs))) / (1.0 + n_surr)
    return {
        "stat": obs,
        "p": p,
        "lag_s": lag_s,
        "lag_abs_err_s": abs(lag_s - LAG_S),
        "direction": 1 if lag_s > 0 else -1,
    }


def detect_cca_fixed(E: np.ndarray, G: np.ndarray, n_surr: int,
                     rng) -> dict:
    n = len(E)
    E = (E - E.mean(axis=0)) / np.maximum(E.std(axis=0, ddof=1), 1e-30)
    G = (G - G.mean(axis=0)) / np.maximum(G.std(axis=0, ddof=1), 1e-30)
    k = int(round(LAG_S / FRAME_DT))
    lags = np.array([k])
    obs = float(_cca_at(E, G, lags)[0])
    null = np.empty(n_surr)
    for j in range(n_surr):
        Gs = common_phase_randomize(G, rng)
        Gs = (Gs - Gs.mean(axis=0)) / np.maximum(
            Gs.std(axis=0, ddof=1), 1e-30)
        null[j] = float(_cca_at(E, Gs, lags)[0])
    p = (1.0 + float(np.sum(null >= obs))) / (1.0 + n_surr)
    return {
        "stat": obs,
        "p": p,
        "lag_s": LAG_S,
        "lag_abs_err_s": 0.0,
        "direction": 1,
    }


def quadratic_terms(P: np.ndarray) -> np.ndarray:
    d = P.shape[1]
    return np.column_stack([P[:, i] * P[:, j]
                            for i in range(d) for j in range(i, d)])


def _fit_ridge(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    G = X.T @ X
    d = X.shape[1]
    G.flat[:: d + 1] += RIDGE_FRAC * np.trace(G) / d
    return np.linalg.solve(G, X.T @ Y)


def _r2_multi(Y: np.ndarray, P: np.ndarray) -> float:
    ss_res = np.sum((Y - P) ** 2, axis=0)
    ss_tot = np.sum((Y - Y.mean(axis=0)) ** 2, axis=0)
    good = ss_tot > 1e-30
    if not np.any(good):
        return 0.0
    return float(np.mean(1.0 - ss_res[good] / ss_tot[good]))


def partial_delayed_gain(Y: np.ndarray, X: np.ndarray, n_surr: int, rng,
                         quadratic: bool) -> dict:
    """R^2 gain of the delayed block over the instantaneous block.

    Linear:    E(t) ~ G(t)              vs  E(t) ~ G(t) + G(t-lag)
    Quadratic: E(t) ~ G(t),Q(G(t)),G(t-lag)
               vs  the same + Q(G(t-lag))
    """
    lag = int(round(LAG_S / FRAME_DT))
    n = len(Y)
    t = np.arange(lag, n)
    y = Y[t].copy()
    Pi = X[t].copy()
    Pd = X[t - lag].copy()
    y -= y.mean(axis=0)
    Pi -= Pi.mean(axis=0)
    Pd -= Pd.mean(axis=0)

    if quadratic:
        Qi = quadratic_terms(Pi)
        X0 = np.hstack([Pi, Qi, Pd])
        X1 = np.hstack([X0, quadratic_terms(Pd)])
    else:
        X0 = Pi
        X1 = np.hstack([Pi, Pd])
    b0 = _fit_ridge(X0, y)
    b1 = _fit_ridge(X1, y)
    gain = _r2_multi(y, X1 @ b1) - _r2_multi(y, X0 @ b0)

    null = np.empty(n_surr)
    for k in range(n_surr):
        Xs = common_phase_randomize(X, rng)
        Xs = (Xs - Xs.mean(axis=0)) / np.maximum(
            Xs.std(axis=0, ddof=1), 1e-30)
        Pi_s = Xs[t] - Xs[t].mean(axis=0)
        Pd_s = Xs[t - lag] - Xs[t - lag].mean(axis=0)
        if quadratic:
            X0s = np.hstack([Pi_s, quadratic_terms(Pi_s), Pd_s])
            X1s = np.hstack([X0s, quadratic_terms(Pd_s)])
        else:
            X0s = Pi_s
            X1s = np.hstack([Pi_s, Pd_s])
        bs0 = _fit_ridge(X0s, y)
        bs1 = _fit_ridge(X1s, y)
        null[k] = _r2_multi(y, X1s @ bs1) - _r2_multi(y, X0s @ bs0)
    p = (1.0 + float(np.sum(null >= gain))) / (1.0 + n_surr)
    return {"gain": float(gain), "p": float(p), "lag_s": LAG_S}


def detect_latent(Ee: np.ndarray, G: np.ndarray, n_surr: int, rng,
                  quadratic: bool) -> dict:
    f = partial_delayed_gain(Ee, G, n_surr, rng, quadratic)
    r = partial_delayed_gain(G, Ee, n_surr, rng, quadratic)
    return {
        "gain_f": f["gain"],
        "p_f": f["p"],
        "gain_r": r["gain"],
        "p_r": r["p"],
        "lag_s": LAG_S,
        "lag_abs_err_s": 0.0,
        "direction": 1 if f["gain"] > r["gain"] else -1,
    }


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------
def run_one(seed: int, coupling: str, rho: float, k_elec: int,
            clean: bool, n_surr: int, keep_exemplar: bool = False,
            block: str = "primary") -> dict:
    t0 = time.time()
    truth = simulate_network(seed)
    graph, D, Q = truth["graph"], truth["D"], truth["Q"]
    n = D.shape[1]
    ntr = int(TRAIN_FRAC * n)

    mu_d = D[:, :ntr].mean(axis=1, keepdims=True)
    sd_d = D[:, :ntr].std(axis=1, ddof=1, keepdims=True)
    h = (D - mu_d) / np.maximum(sd_d, 1e-30)
    W = camera_weights(graph["pts"], graph["edges"])
    rng_cam = np.random.default_rng(seed + 3)
    noise = 0.0 if clean else CAMERA_NOISE
    image = (h.T @ W.T) + noise * rng_cam.normal(size=(n, len(W)))
    pod = pod_scores(image)
    G = pod["G"]

    elec = electrical_observation(seed, graph, D, coupling, rho, k_elec,
                                  clean=clean)
    Ee = elec["Ee"]

    d1 = detect_scalar_direct(Ee[:, 0], G[:, 0], n_surr,
                              np.random.default_rng(seed + 10))
    d2 = detect_cca_at_lag(Ee, G, n_surr,
                           np.random.default_rng(seed + 11))
    d1f = detect_scalar_fixed(Ee[:, 0], G[:, 0], n_surr,
                              np.random.default_rng(seed + 14))
    d2f = detect_cca_fixed(Ee, G, n_surr,
                           np.random.default_rng(seed + 15))
    l1 = detect_latent(Ee, G, n_surr, np.random.default_rng(seed + 12),
                       quadratic=False)
    l2 = detect_latent(Ee, G, n_surr, np.random.default_rng(seed + 13),
                       quadratic=True)

    rec = {
        "block": block,
        "seed": int(seed),
        "coupling": coupling,
        "rho": float(rho),
        "k_elec": int(k_elec),
        "clean": bool(clean),
        "graph": {
            "n_nodes": GRAPH_NODES,
            "n_edges": len(graph["edges"]),
            "sources": graph["sources"].tolist(),
            "sinks": graph["sinks"].tolist(),
        },
        "pod": {
            "r90": pod["r90"],
            "r": pod["r"],
            "var_frac_top": pod["var_frac_top"],
        },
        "elec": {
            "q": elec["q"],
            "var_top": elec["elec_var_top"],
        },
        "d1": d1,
        "d2": d2,
        "d1f": d1f,
        "d2f": d2f,
        "l1": l1,
        "l2": l2,
        "runtime_s": float(time.time() - t0),
    }
    if keep_exemplar:
        rec["_exemplar"] = {
            "D": D.astype(np.float32),
            "Q": Q.astype(np.float32),
            "G": G.astype(np.float32),
            "Ee": Ee.astype(np.float32),
            "W": W.astype(np.float32),
            "pod_basis": pod["basis"].astype(np.float32),
            "pts": graph["pts"],
            "edges": np.array(graph["edges"], dtype=int),
            "sources": graph["sources"],
            "sinks": graph["sinks"],
        }
    return rec


# ---------------------------------------------------------------------------
# Summaries and decision
# ---------------------------------------------------------------------------
def _detected(rec: dict, det: str) -> bool:
    if det in ("d1", "d2", "d1f", "d2f"):
        return rec[det]["p"] < ALPHA
    return rec[det]["p_f"] < ALPHA


def summarize(records: list[dict], block: str = "primary") -> dict:
    records = [r for r in records if r.get("block", "primary") == block]
    out: dict = {}
    keys = sorted({(r["coupling"], r["rho"]) for r in records})
    for coupling, rho in keys:
        recs = [r for r in records if r["coupling"] == coupling
                and r["rho"] == rho]
        n = len(recs)
        cell = {"n": n}
        for det in ALL_DETECTORS:
            det_recs = [r for r in recs if _detected(r, det)]
            cell[det] = {
                "power": len(det_recs) / n if n else float("nan"),
                "detected": len(det_recs),
                "lag_recovered": (
                    float(np.mean([r[det]["lag_abs_err_s"] <= LAG_TOL_S
                                   for r in det_recs]))
                    if det_recs else float("nan")
                ),
                "lag_median_s": (
                    float(np.median([r[det]["lag_s"] for r in det_recs]))
                    if det_recs else float("nan")
                ),
                "direction_correct": (
                    float(np.mean([r[det]["direction"] > 0
                                   for r in det_recs]))
                    if det_recs else float("nan")
                ),
            }
            if det in ("l1", "l2"):
                cell[det]["reverse_power"] = float(np.mean(
                    [r[det]["p_r"] < ALPHA for r in recs]))
        out[f"{coupling}|{rho:.1f}"] = cell
    return out


def summarize_sweep(records: list[dict], block: str = "secondary") -> dict:
    """Descriptive K sweep: one cell per (coupling, rho, K)."""
    records = [r for r in records if r.get("block", "primary") == block]
    out: dict = {}
    keys = sorted({(r["coupling"], r["rho"], r["k_elec"]) for r in records})
    for coupling, rho, k in keys:
        recs = [r for r in records if r["coupling"] == coupling
                and r["rho"] == rho and r["k_elec"] == k]
        n = len(recs)
        cell = {"n": n, "k_elec": k}
        for det in MAIN_DETECTORS:
            det_recs = [r for r in recs if _detected(r, det)]
            cell[det] = {
                "power": len(det_recs) / n if n else float("nan"),
                "detected": len(det_recs),
                "direction_correct": (
                    float(np.mean([r[det]["direction"] > 0
                                   for r in det_recs]))
                    if det_recs else float("nan")
                ),
            }
        out[f"{coupling}|{rho:.1f}|K{k}"] = cell
    return out


def pooled_fpr(records: list[dict], block: str = "primary") -> dict:
    nulls = [r for r in records if r.get("block", "primary") == block
             and r["rho"] == 0.0]
    n = len(nulls)
    out = {}
    for det in ALL_DETECTORS:
        k = sum(_detected(r, det) for r in nulls)
        out[det] = {"n": n, "fpr": k / n if n else float("nan"),
                    "detected": k}
    return out


def stat_name(det: str) -> str:
    if det in ("d1", "d2", "d1f", "d2f"):
        return "stat"
    return "gain_f"


def thresholds_from_null(records: list[dict],
                         block: str = "primary") -> dict:
    nulls = [r for r in records if r.get("block", "primary") == block
             and r["rho"] == 0.0]
    out = {}
    for det in ALL_DETECTORS:
        vals = [r[det][stat_name(det)] for r in nulls]
        out[det] = float(np.quantile(vals, 0.95)) if vals else float("nan")
    return out


def matched_power(records: list[dict], thresholds: dict,
                  block: str = "primary") -> dict:
    records = [r for r in records if r.get("block", "primary") == block]
    out: dict = {}
    keys = sorted({(r["coupling"], r["rho"]) for r in records})
    for coupling, rho in keys:
        recs = [r for r in records if r["coupling"] == coupling
                and r["rho"] == rho]
        cell = {}
        for det in ALL_DETECTORS:
            cell[det] = float(np.mean(
                [r[det][stat_name(det)] >= thresholds[det] for r in recs]))
        out[f"{coupling}|{rho:.1f}"] = cell
    return out


def verdict(summary: dict) -> dict:
    candidates = [0.5, 0.7, 0.9]
    informative = None
    for rho in reversed(candidates):
        cell = summary.get(f"quadratic|{rho:.1f}")
        if cell is None:
            continue
        best = max(cell[d]["power"] for d in MAIN_DETECTORS)
        if np.isfinite(best) and best >= INFORMATIVE_POWER:
            informative = rho
            break
    if informative is None:
        return {
            "status": "UNDETERMINED: no detector reached power >= 0.5 at "
                      "rho in {0.5, 0.7, 0.9}; testbed underpowered",
            "informative_rho": None,
        }

    cell = summary[f"quadratic|{informative:.1f}"]
    powers = {d: cell[d]["power"] for d in MAIN_DETECTORS}
    direct = max(powers["d1"], powers["d2"])
    latent = max(powers["l1"], powers["l2"])
    best_latent = "l1" if powers["l1"] >= powers["l2"] else "l2"
    lag_rec = cell[best_latent]["lag_recovered"]
    dir_ok = cell[best_latent]["direction_correct"]

    linear_cell = summary.get(f"linear|{informative:.1f}", {})
    l2_linear = linear_cell.get("l2", {}).get("power", float("nan"))
    specificity = not (np.isfinite(l2_linear)
                       and l2_linear >= SPECIFICITY_MAX)

    linear_l1 = linear_cell.get("l1", {}).get("power", float("nan"))
    linear_direct = max(linear_cell.get("d1", {}).get("power", 0.0),
                        linear_cell.get("d2", {}).get("power", 0.0))

    if (latent >= direct + POWER_MARGIN
            and np.isfinite(dir_ok) and dir_ok >= DIRECTION_MIN
            and specificity):
        status = ("LATENT ADDS VALUE: max latent power exceeds best direct "
                  "detector by >= 0.20 with acceptable direction and L2 "
                  "specificity")
    elif latent >= direct + POWER_MARGIN and not specificity:
        status = ("NO ADDED VALUE: latent power margin is met, but L2 also "
                  "detects the linear cell; the nonlinear layer is not "
                  "specific")
    else:
        status = ("NO ADDED VALUE: latent pipeline fails the pre-registered "
                  "margin; downgrade per R1 kill criterion")

    return {
        "status": status,
        "informative_rho": informative,
        "powers": powers,
        "best_direct": direct,
        "best_latent": latent,
        "best_latent_detector": best_latent,
        "lag_recovered_best_latent": lag_rec,
        "direction_correct_best_latent": dir_ok,
        "l2_linear_power": l2_linear,
        "l2_specific": bool(specificity),
        "linear_cell_l1": linear_l1,
        "linear_cell_direct": linear_direct,
    }


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
def write_outputs(records: list[dict], outdir: str, args, runtime_s: float):
    os.makedirs(outdir, exist_ok=True)
    primary = [r for r in records if r.get("block", "primary") == "primary"]
    secondary = [r for r in records if r.get("block") == "secondary"]
    positive = [r for r in records if r.get("block") == "positive"]

    summary = summarize(primary)
    fpr = pooled_fpr(primary)
    thresholds = thresholds_from_null(primary)
    matched = matched_power(primary, thresholds)
    decision = verdict(summary) if any(
        r["coupling"] == "quadratic" and r["rho"] > 0 for r in primary
    ) else {}
    sweep = summarize_sweep(secondary) if secondary else {}
    positive_summary = summarize(positive, block="positive") if positive else {}

    exemplars = {}
    for rec in records:
        ex = rec.pop("_exemplar", None)
        if ex is not None:
            name = (f"exemplar_{rec['coupling']}_"
                    f"rho{int(round(rec['rho']*10)):02d}.npz")
            np.savez_compressed(os.path.join(outdir, name), **ex)
            exemplars[name] = rec["seed"]

    with open(os.path.join(outdir, "s1_results.json"), "w") as f:
        json.dump({
            "primary": {"summary": summary, "fpr": fpr,
                        "thresholds": thresholds, "matched_power": matched,
                        "decision": decision},
            "secondary": {"summary": sweep},
            "positive": {"summary": positive_summary},
            "records": records,
        }, f, indent=2)

    fields = ["block", "coupling", "rho", "seed", "k_elec", "clean",
              "pod_r90", "pod_r", "elec_q"]
    for det in ALL_DETECTORS:
        if det in ("d1", "d2", "d1f", "d2f"):
            fields += [f"{det}_p", f"{det}_stat", f"{det}_lag_s"]
        else:
            fields += [f"{det}_p_f", f"{det}_p_r", f"{det}_gain_f",
                       f"{det}_gain_r"]
    with open(os.path.join(outdir, "s1_results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            row = {"block": r["block"],
                   "coupling": r["coupling"], "rho": r["rho"],
                   "seed": r["seed"], "k_elec": r["k_elec"],
                   "clean": r["clean"], "pod_r90": r["pod"]["r90"],
                   "pod_r": r["pod"]["r"], "elec_q": r["elec"]["q"]}
            for det in ("d1", "d2", "d1f", "d2f"):
                row[f"{det}_p"] = r[det]["p"]
                row[f"{det}_stat"] = r[det]["stat"]
                row[f"{det}_lag_s"] = r[det]["lag_s"]
            for det in ("l1", "l2"):
                row[f"{det}_p_f"] = r[det]["p_f"]
                row[f"{det}_p_r"] = r[det]["p_r"]
                row[f"{det}_gain_f"] = r[det]["gain_f"]
                row[f"{det}_gain_r"] = r[det]["gain_r"]
            w.writerow(row)

    couplings = sorted({r["coupling"] for r in records})
    fig, axes = plt.subplots(1, len(couplings),
                             figsize=(4.6 * len(couplings), 3.6),
                             dpi=140, squeeze=False)
    for ax, coupling in zip(axes[0], couplings):
        rhos = sorted({r["rho"] for r in records
                       if r["coupling"] == coupling})
        for det, label, style in (
            ("d1", "D1 scalar direct", "s--"),
            ("d2", "D2 CCA-at-lag", "^:"),
            ("l1", "L1 partial linear", "o-"),
            ("l2", "L2 partial quadratic", "d-"),
        ):
            ys = []
            for rho in rhos:
                cell = summary.get(f"{coupling}|{rho:.1f}")
                ys.append(cell[det]["power"] if cell else np.nan)
            ax.plot(rhos, ys, style, label=label, markersize=4)
        ax.set_xlabel("rho (model parameter)")
        ax.set_ylabel("detection rate (p < 0.05)")
        ax.set_ylim(-0.03, 1.03)
        ax.grid(alpha=0.3)
        ax.set_title(f"coupling: {coupling}")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "s1_power.png"))

    with open(os.path.join(outdir, "s1_summary.md"), "w") as f:
        f.write("# S1 — high-dimensional / nonlinear network testbed\n\n")
        f.write("Evidence label: **computed (model-internal)**. `rho` is a "
                "model parameter, not a biological measurement; no "
                "experimental claim.\n\n")
        f.write("Pre-registered design: see the module docstring and "
                "`run_meta.json`; alpha = 0.05, lag = 600 s, tolerance "
                f"±120 s, surrogates = {args.n_surr}.\n\n")
        f.write("## Primary grid — detection rate\n\n")
        f.write("| coupling | rho | n | D1 | D2 | D1f | D2f | L1 | L2 | "
                "L1 rev | L2 rev |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for key in sorted(summary):
            c = summary[key]
            coupling, rho = key.split("|")
            f.write(
                f"| {coupling} | {rho} | {c['n']} | "
                f"{c['d1']['power']:.3f} | {c['d2']['power']:.3f} | "
                f"{c['d1f']['power']:.3f} | {c['d2f']['power']:.3f} | "
                f"{c['l1']['power']:.3f} | {c['l2']['power']:.3f} | "
                f"{c['l1']['reverse_power']:.3f} | "
                f"{c['l2']['reverse_power']:.3f} |\n")
        f.write("\n## Lag and direction among detected runs\n\n")
        f.write("| coupling | rho | detector | detected | "
                "lag recovered | median lag (s) | direction correct |\n")
        f.write("|---|---:|---|---:|---:|---:|---:|\n")
        for key in sorted(summary):
            c = summary[key]
            coupling, rho = key.split("|")
            for det in ALL_DETECTORS:
                d = c[det]
                if d["detected"] == 0:
                    continue
                f.write(
                    f"| {coupling} | {rho} | {det.upper()} | "
                    f"{d['detected']}/{c['n']} | "
                    f"{d['lag_recovered']:.3f} | {d['lag_median_s']:.0f} | "
                    f"{d['direction_correct']:.3f} |\n")
        f.write("\n## Empirical false-positive rate at rho = 0\n\n")
        f.write("| detector | detected / n | FPR | threshold (95th pct) |\n")
        f.write("|---|---:|---:|---:|\n")
        for det in ALL_DETECTORS:
            e = fpr[det]
            f.write(f"| {det.upper()} | {e['detected']}/{e['n']} | "
                    f"{e['fpr']:.3f} | {thresholds[det]:.4g} |\n")
        f.write("\nMatched-threshold power (used only if FPR outside "
                "[0.02, 0.10]):\n\n")
        f.write("| cell | D1 | D2 | L1 | L2 |\n|---|---:|---:|---:|---:|\n")
        for key in sorted(matched):
            m = matched[key]
            f.write(f"| {key} | {m['d1']:.3f} | {m['d2']:.3f} | "
                    f"{m['l1']:.3f} | {m['l2']:.3f} |\n")
        if sweep:
            f.write("\n## Secondary grid — K sweep (descriptive)\n\n")
            f.write("| cell | n | D1 | D2 | L1 | L2 |\n")
            f.write("|---|---:|---:|---:|---:|---:|\n")
            for key in sorted(sweep):
                c = sweep[key]
                f.write(f"| {key} | {c['n']} | {c['d1']['power']:.3f} | "
                        f"{c['d2']['power']:.3f} | "
                        f"{c['l1']['power']:.3f} | "
                        f"{c['l2']['power']:.3f} |\n")
        if positive_summary:
            f.write("\n## Positive controls (clean, rho=1; diagnostic)\n\n")
            f.write("| cell | n | D1 | D2 | L1 | L2 |\n")
            f.write("|---|---:|---:|---:|---:|---:|\n")
            for key in sorted(positive_summary):
                c = positive_summary[key]
                f.write(f"| {key} | {c['n']} | {c['d1']['power']:.3f} | "
                        f"{c['d2']['power']:.3f} | "
                        f"{c['l1']['power']:.3f} | "
                        f"{c['l2']['power']:.3f} |\n")
        if decision:
            f.write("\n## Pre-registered verdict\n\n")
            f.write(f"- Status: **{decision['status']}**\n")
            if decision.get("informative_rho") is not None:
                f.write(f"- Informative rho: "
                        f"{decision['informative_rho']:.1f}\n")
                f.write(f"- Powers: "
                        f"{json.dumps(decision['powers'], ensure_ascii=False)}\n")
                f.write(f"- Best direct = {decision['best_direct']:.3f}; "
                        f"best latent = {decision['best_latent']:.3f} "
                        f"({decision['best_latent_detector'].upper()})\n")
                f.write(f"- Lag recovered (best latent) = "
                        f"{decision['lag_recovered_best_latent']:.3f}; "
                        f"direction correct = "
                        f"{decision['direction_correct_best_latent']:.3f}\n")
                f.write(f"- L2 linear-cell power = "
                        f"{decision['l2_linear_power']:.3f} "
                        f"(specific = {decision['l2_specific']})\n")
        f.write("\n## Notes\n\n")
        f.write("- Positive-control and secondary-grid runs, when present "
                "in `s1_results.json`, are separate record blocks; the "
                "verdict above uses the primary grid only.\n")
        f.write("- The truth model is a stationary log-homeostatic TK "
                "variant, a testbed device, not a biological claim.\n")
        f.write("- The 100 uV carrier makes instrument noise subdominant; "
                "the 20 uV detectability question belongs to S0.\n")
        f.write("- POD uses the training segment only; the 90% variance "
                f"rule is capped at {CAMERA_R_MAX} modes.\n")
        f.write("- The camera sees D linearly; the quadratic coupling is "
                "invisible to linear statistics by construction.\n")
        f.write("- `rho` is a model parameter; S1 cannot replace the four "
                "experimental controls.\n")

    meta = {
        "script": os.path.basename(__file__),
        "script_sha256": hashlib.sha256(
            open(os.path.abspath(__file__), "rb").read()).hexdigest(),
        "python": sys.version,
        "numpy": np.__version__,
        "args": vars(args),
        "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "runtime_s": runtime_s,
        "exemplars": exemplars,
        "constants": {k: v for k, v in globals().items()
                      if k.isupper() and isinstance(
                          v, (int, float, str, tuple, list))},
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

    return summary, fpr, decision


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def jobs_for(grid: str) -> list[tuple]:
    jobs = []
    if grid in ("primary", "all"):
        for coupling in PRIMARY_COUPLINGS:
            for rho in PRIMARY_RHO:
                for sim in range(PRIMARY_N):
                    jobs.append(("primary", coupling, rho, ELEC_K, False, sim))
    if grid in ("secondary", "all"):
        for k in SECONDARY_K:
            for rho in SECONDARY_RHO:
                for sim in range(SECONDARY_N):
                    jobs.append(("secondary", "quadratic", rho, k, False,
                                 sim))
    if grid in ("positive", "all"):
        for coupling in PRIMARY_COUPLINGS:
            for sim in range(CLEAN_N):
                jobs.append(("positive", coupling, CLEAN_RHO, ELEC_K, True,
                             sim))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="results/s1_network")
    ap.add_argument("--grid", choices=("primary", "secondary", "positive",
                                       "all"), default="primary")
    ap.add_argument("--n-sims", type=int, default=None)
    ap.add_argument("--n-surr", type=int, default=N_SURR)
    ap.add_argument("--max-runs", type=int, default=None,
                    help="debug: stop after this many runs")
    ap.add_argument("--pilot", action="store_true",
                    help="one run per cell, prints diagnostics")
    args = ap.parse_args()

    jobs = jobs_for(args.grid)
    if args.pilot:
        pilot = []
        seen = set()
        for job in jobs:
            key = (job[1], job[2], job[3], job[4])
            if key not in seen:
                seen.add(key)
                pilot.append(job)
        jobs = pilot
    if args.n_sims is not None:
        jobs = [j for j in jobs if j[5] < args.n_sims]
    if args.max_runs is not None:
        jobs = jobs[: args.max_runs]

    t0 = time.time()
    records = []
    for idx, (block, coupling, rho, k, clean, sim) in enumerate(jobs):
        seed = seed_for(block, coupling, k, sim, rho)
        keep = (block == "primary" and abs(rho - 0.9) < 1e-9 and sim == 0)
        rec = run_one(seed, coupling, rho, k, clean, args.n_surr,
                      keep_exemplar=keep, block=block)
        records.append(rec)
        print(
            f"[{idx+1}/{len(jobs)}] {block} {coupling} rho={rho:.1f} "
            f"K={k} seed={seed} "
            f"D1 p={rec['d1']['p']:.3f} lag={rec['d1']['lag_s']:.0f} "
            f"D2 p={rec['d2']['p']:.3f} lag={rec['d2']['lag_s']:.0f} "
            f"L1 p={rec['l1']['p_f']:.3f}/{rec['l1']['p_r']:.3f} "
            f"L2 p={rec['l2']['p_f']:.3f}/{rec['l2']['p_r']:.3f} "
            f"({rec['runtime_s']:.1f}s)",
            flush=True,
        )

    runtime_s = time.time() - t0
    summary, fpr, decision = write_outputs(records, args.outdir, args,
                                           runtime_s)
    print(f"\nwrote {args.outdir} in {runtime_s:.1f} s")
    print(json.dumps({"fpr": fpr, "decision": decision}, indent=2))


if __name__ == "__main__":
    main()
