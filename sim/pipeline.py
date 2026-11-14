#!/usr/bin/env python3
"""Analysis pipeline and detection statistics for S0.

Two statistics:
  - spontaneous: band-passed amplitude vs structural observation, max |r| over
    lags, tested against phase-randomised surrogates.
  - driven: fundamental (and low harmonics) of the amplitude folded at the
    drive period, tested against circular-shift surrogates.
"""
from __future__ import annotations

import numpy as np
from scipy import signal


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 4) -> np.ndarray:
    hi = min(hi, 0.45 * fs)
    sos = signal.butter(order, [lo, hi], btype="bandpass", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x)


def analytic_amplitude(x: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    xb = bandpass(x, fs, lo, hi)
    return np.abs(signal.hilbert(xb))


def extract_observable(
    e_mv: np.ndarray,
    t: np.ndarray,
    f_lo: float,
    f_hi: float,
    observable: str = "potential",
) -> np.ndarray:
    """Band-passed signed potential or its Hilbert envelope."""
    fs = 1.0 / np.median(np.diff(t))
    if observable == "potential":
        return bandpass(e_mv, fs, f_lo, f_hi)
    if observable == "envelope":
        return analytic_amplitude(e_mv, fs, f_lo, f_hi)
    raise ValueError(f"unknown observable: {observable}")


def xcorr_lag(x: np.ndarray, y: np.ndarray, max_lag_samples: int):
    """Normalised cross-correlation for lags in [-max_lag, +max_lag]."""
    x = (x - x.mean()) / (x.std(ddof=1) + 1e-30)
    y = (y - y.mean()) / (y.std(ddof=1) + 1e-30)
    n = len(x)
    c = signal.correlate(x, y, mode="full", method="fft") / n
    lags = np.arange(-n + 1, n)
    keep = np.abs(lags) <= max_lag_samples
    return lags[keep], c[keep]


def phase_randomize(x: np.ndarray, rng) -> np.ndarray:
    """Surrogate with the same power spectrum and randomised phases."""
    X = np.fft.rfft(x)
    phases = rng.uniform(0.0, 2.0 * np.pi, len(X))
    phases[0] = 0.0
    if len(x) % 2 == 0:
        phases[-1] = 0.0
    return np.fft.irfft(np.abs(X) * np.exp(1j * phases), n=len(x))


def block_bootstrap(x: np.ndarray, block_len: int, rng) -> np.ndarray:
    """Circular block bootstrap: keeps short-range autocorrelation, breaks a
    long-period driven component (used as the driven-mode null)."""
    n = len(x)
    block_len = max(1, min(block_len, n))
    n_blocks = int(np.ceil(n / block_len))
    starts = rng.integers(0, n, size=n_blocks)
    idx = (starts[:, None] + np.arange(block_len)[None, :]) % n
    return x[idx.ravel()][:n]


def detect_spontaneous(
    e_mv: np.ndarray,
    t: np.ndarray,
    s_obs: np.ndarray,
    t_s: np.ndarray,
    f_lo: float = 0.01,
    f_hi: float = 0.1,
    max_lag_s: float = 1800.0,
    n_surr: int = 200,
    observable: str = "potential",
    seed: int = 0,
) -> dict:
    rng = np.random.default_rng(seed)
    sig = extract_observable(e_mv, t, f_lo, f_hi, observable)
    amp_s = np.interp(t_s, t, sig)

    frame_dt = float(np.median(np.diff(t_s)))
    max_lag = int(round(max_lag_s / frame_dt))
    lags, r = xcorr_lag(amp_s, s_obs, max_lag)
    idx = int(np.argmax(np.abs(r)))
    obs_r = float(r[idx])
    obs_lag_s = float(lags[idx] * frame_dt)

    null = np.empty(n_surr)
    for k in range(n_surr):
        s_surr = phase_randomize(s_obs, rng)
        _, r_surr = xcorr_lag(amp_s, s_surr, max_lag)
        null[k] = np.max(np.abs(r_surr))
    p = (1.0 + float(np.sum(null >= abs(obs_r)))) / (1.0 + n_surr)

    return {
        "stat": abs(obs_r),
        "r": obs_r,
        "lag_s": obs_lag_s,
        "p": p,
        "n_surr": n_surr,
        "null_p95": float(np.quantile(null, 0.95)),
    }


def detect_driven(
    e_mv: np.ndarray,
    t: np.ndarray,
    t_s: np.ndarray,
    period_s: float,
    f_lo: float = 0.01,
    f_hi: float = 0.1,
    n_harm: int = 3,
    n_surr: int = 200,
    block_s: float = 1800.0,
    observable: str = "potential",
    seed: int = 0,
) -> dict:
    rng = np.random.default_rng(seed)
    sig = extract_observable(e_mv, t, f_lo, f_hi, observable)
    amp_raw = np.interp(t_s, t, sig)
    amp_std = float(np.std(amp_raw, ddof=1))
    amp_s = (amp_raw - amp_raw.mean()) / (amp_std + 1e-30)

    phase = 2.0 * np.pi * (t_s % period_s) / period_s

    def stat_of(x: np.ndarray) -> float:
        return float(
            sum(
                np.abs(np.mean(x * np.exp(-1j * k * phase))) ** 2
                for k in range(1, n_harm + 1)
            )
        )

    obs = stat_of(amp_s)
    frame_dt = float(np.median(np.diff(t_s)))
    block_len = max(1, int(round(block_s / frame_dt)))
    null = np.empty(n_surr)
    for k in range(n_surr):
        null[k] = stat_of(block_bootstrap(amp_s, block_len, rng))
    p = (1.0 + float(np.sum(null >= obs))) / (1.0 + n_surr)

    # Report the fundamental response amplitude (peak) and phase.
    z1 = np.mean(amp_s * np.exp(-1j * phase))
    amp_uv = float(amp_std * 2.0 * abs(z1) * 1e3)  # original uV units

    return {
        "stat": obs,
        "p": p,
        "response_uv": amp_uv,
        "phase_rad": float(np.angle(z1)),
        "n_surr": n_surr,
        "null_p95": float(np.quantile(null, 0.95)),
    }
