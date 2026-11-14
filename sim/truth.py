#!/usr/bin/env python3
"""Minimal physical truth model for S0 detectability.

Two time scales:
  - s(t): slow structural state (OU process, correlation time tau_s), optionally
    driven by a square wave (food-source switching).
  - a(t): electrical activity amplitude = rho * s(t - lag) + independent fast OU.

The measured potential is an amplitude-modulated carrier:
    V(t) = A * a(t) * cos(2*pi*f0*t + phi0)

This is a *phenomenological* model, not a claim about Physarum.  Its job is to
map a hypothesised coupling to an observable, and to expose which nuisance
terms limit detectability.
"""
from __future__ import annotations

import numpy as np
from scipy import signal


def ou_process(n: int, fs: float, tau_s: float, rng, sigma: float = 1.0) -> np.ndarray:
    """Exact AR(1) discretisation of an OU process with stationary std sigma."""
    a = np.exp(-1.0 / (fs * tau_s))
    b = sigma * np.sqrt(1.0 - a * a)
    x = signal.lfilter([b], [1.0, -a], rng.normal(size=n))
    return x


def delayed(x: np.ndarray, delay_samples: int) -> np.ndarray:
    """y[t] = x[t - delay]; the first delay samples hold x[0]."""
    if delay_samples <= 0:
        return x.copy()
    y = np.empty_like(x)
    y[:delay_samples] = x[0]
    y[delay_samples:] = x[:-delay_samples]
    return y


def make_run(
    duration_s: float,
    fs: float = 1.0,
    frame_dt: float = 10.0,
    rho: float = 0.0,
    lag_s: float = 600.0,
    tau_s: float = 7200.0,
    tau_e: float = 1800.0,
    f0: float = 0.03,
    signal_uv: float = 20.0,
    signal_model: str = "potential",
    mode: str = "spontaneous",
    drive_period_s: float = 7200.0,
    drive_amp: float = 1.0,
    tau_drive_s: float | None = None,
    sigma_s_obs: float = 0.3,
    seed: int = 0,
) -> dict:
    """Generate one synthetic experiment (truth + structural observation)."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * fs)
    t = np.arange(n, dtype=float) / fs

    # Slow structural state.  The drive is low-passed by the network response
    # time (default: tau_s), so a fast drive is attenuated rather than followed
    # instantaneously.
    s = ou_process(n, fs, tau_s, rng)
    if mode == "driven":
        drive = signal.square(2.0 * np.pi * t / drive_period_s, duty=0.5)
        tau_d = tau_s if tau_drive_s is None else tau_drive_s
        a_d = np.exp(-1.0 / (fs * tau_d))
        drive_f = signal.lfilter([1.0 - a_d], [1.0, -a_d], drive)
        s = s + drive_amp * drive_f
    elif mode != "spontaneous":
        raise ValueError(f"unknown mode: {mode}")

    # Electrical amplitude: delayed structural copy + independent fast noise.
    s_del = delayed(s, int(round(lag_s * fs)))
    a = rho * s_del + np.sqrt(max(0.0, 1.0 - rho * rho)) * ou_process(n, fs, tau_e, rng)
    a = a / a.std(ddof=1)

    # Measured differential potential (mV).  "potential" is the signed slow
    # extracellular signal; "am" is a positive oscillation envelope.
    if signal_model == "potential":
        e_mv = (signal_uv / 1e3) * a
    elif signal_model == "am":
        phi0 = rng.uniform(0.0, 2.0 * np.pi)
        a_pos = np.exp(0.5 * a)
        e_mv = (signal_uv / 1e3) * a_pos * np.cos(2.0 * np.pi * f0 * t + phi0)
    else:
        raise ValueError(f"unknown signal_model: {signal_model}")

    # Structural observation at the camera frame rate.
    t_s = np.arange(0.0, duration_s, frame_dt)
    s_at_frames = np.interp(t_s, t, s)
    s_obs = s_at_frames + sigma_s_obs * rng.normal(size=len(t_s))

    realized_r = float(np.corrcoef(a, s_del)[0, 1])
    return {
        "t": t,
        "e_mv": e_mv,
        "s": s,
        "t_s": t_s,
        "s_obs": s_obs,
        "truth": {
            "rho": rho,
            "lag_s": lag_s,
            "realized_r": realized_r,
            "mode": mode,
            "drive_period_s": drive_period_s if mode == "driven" else None,
            "drive_amp": drive_amp if mode == "driven" else None,
            "tau_drive_s": (tau_s if tau_drive_s is None else tau_drive_s)
            if mode == "driven"
            else None,
            "f0": f0,
            "signal_uv": signal_uv,
            "signal_model": signal_model,
            "tau_s": tau_s,
            "tau_e": tau_e,
        },
        "meta": {"fs": fs, "frame_dt": frame_dt, "duration_s": duration_s, "seed": seed},
    }
