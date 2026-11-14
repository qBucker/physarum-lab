#!/usr/bin/env python3
"""Instrument forward model for the Physarum phase-0 signal chain.

All parameters are ASSUMED / PROJECTED unless explicitly marked.  The model is
deliberately simple and calibratable by bench tests T1-T6.

Units: time in seconds, potentials in millivolts (mV).

Reference points
----------------
- ADS1256 datasheet, Table 1 (buffer on, inputs shorted, VREF=2.5 V, 25 C):
  10 SPS / PGA=8 -> 0.106 uV RMS input-referred noise.
- Module input impedance: 1 MOhm (ADS1256 itself; the module has 100 Ohm series).
- At 10 SPS the digital filter notches 50 Hz; at 1 kSPS mains must be modelled.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

K_B = 1.380649e-23
T_K = 300.0

# ADS1256 Table 1, 10 SPS, buffer on, inputs shorted (uV RMS).
_ADC_NOISE_10SPS_UV = {
    1: 0.339,
    2: 0.214,
    4: 0.138,
    8: 0.106,
    16: 0.082,
    32: 0.061,
    64: 0.061,
}


@dataclass
class ElectrodeModel:
    """Two-electrode differential interface (electrode + agar bridge)."""

    z_source_ohm: float = 10e3
    half_cell_mv: float = 0.0
    drift_mv_per_h: float = 0.0
    flicker_uv_rms: float = 0.0
    flicker_beta: float = 1.0
    # In-band RMS is defined over this band; outside it the flicker is zero.
    flicker_band: tuple = (0.01, 0.1)


@dataclass
class ADCModel:
    fs: float = 1.0
    vref: float = 2.5
    pga: float = 8.0
    bits: int = 24
    z_in_ohm: float = 1e6
    cmrr_db: float = 100.0
    mains_uv: float = 0.0
    mains_hz: float = 50.0

    @property
    def lsb_mv(self) -> float:
        return 2.0 * self.vref / (self.pga * (2 ** self.bits)) * 1e3

    @property
    def full_scale_mv(self) -> float:
        return self.vref / self.pga * 1e3

    def rms_noise_uv(self) -> float:
        """Interpolate the datasheet 10 SPS value, scale as sqrt(fs/10)."""
        base = _ADC_NOISE_10SPS_UV[int(self.pga)]
        scale = np.sqrt(max(self.fs, 1.0) / 10.0)
        return base * scale


def pink_noise(
    n: int,
    fs: float,
    rms: float,
    beta: float = 1.0,
    rng=None,
    band=None,
) -> np.ndarray:
    """Generate 1/f^beta noise with the requested time-domain RMS.

    If band=(lo, hi) is given, the spectrum is zero outside that band and the
    requested RMS is the in-band RMS.
    """
    if rms <= 0:
        return np.zeros(n)
    rng = np.random.default_rng() if rng is None else rng
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    amp = np.zeros_like(freqs)
    amp[1:] = freqs[1:] ** (-beta / 2.0)
    if band is not None:
        lo, hi = band
        amp[(freqs < lo) | (freqs > hi)] = 0.0
    phase = rng.uniform(0.0, 2.0 * np.pi, len(freqs))
    spec = amp * np.exp(1j * phase)
    x = np.fft.irfft(spec, n=n)
    x -= x.mean()
    sd = x.std(ddof=1)
    return x * (rms / sd) if sd > 0 else x


def thermal_noise_uv(r_ohm: float, bw_hz: float) -> float:
    return np.sqrt(4.0 * K_B * T_K * r_ohm * bw_hz) * 1e6


def measure(
    v_true_mv: np.ndarray,
    t: np.ndarray,
    elec: ElectrodeModel,
    adc: ADCModel,
    rng=None,
) -> np.ndarray:
    """Apply the measurement chain to a true differential potential (mV)."""
    rng = np.random.default_rng() if rng is None else rng
    n = len(v_true_mv)
    fs = adc.fs

    # Source-impedance loading.
    v = v_true_mv * (adc.z_in_ohm / (adc.z_in_ohm + elec.z_source_ohm))

    # Half-cell offset + linear drift.
    v = v + elec.half_cell_mv
    if elec.drift_mv_per_h:
        v = v + elec.drift_mv_per_h * (t - t[0]) / 3600.0

    # Electrode 1/f noise (in-band RMS, mV).
    if elec.flicker_uv_rms:
        v = v + pink_noise(
            n,
            fs,
            elec.flicker_uv_rms / 1e3,
            elec.flicker_beta,
            rng,
            band=elec.flicker_band,
        )

    # Thermal noise of the source (full Nyquist band).
    v = v + rng.normal(0.0, thermal_noise_uv(elec.z_source_ohm, fs / 2.0) / 1e3, n)

    # ADC input-referred noise.
    v = v + rng.normal(0.0, adc.rms_noise_uv() / 1e3, n)

    # Mains: common-mode to differential via finite CMRR.  At 10 SPS the
    # digital filter notches 50 Hz, so callers should leave mains_uv=0 there.
    if adc.mains_uv:
        cm_to_diff = 10.0 ** (-adc.cmrr_db / 20.0)
        v = v + adc.mains_uv / 1e3 * cm_to_diff * np.sin(
            2.0 * np.pi * adc.mains_hz * t
        )

    # Quantization + saturation.
    v = np.clip(v, -adc.full_scale_mv, adc.full_scale_mv)
    v = np.round(v / adc.lsb_mv) * adc.lsb_mv
    return v


def describe(elec: ElectrodeModel, adc: ADCModel) -> dict:
    d = {
        "electrode": asdict(elec),
        "adc": asdict(adc),
        "adc_lsb_mv": adc.lsb_mv,
        "adc_full_scale_mv": adc.full_scale_mv,
        "adc_rms_noise_uv": adc.rms_noise_uv(),
        "thermal_noise_uv": thermal_noise_uv(elec.z_source_ohm, adc.fs / 2.0),
        "loading_factor": adc.z_in_ohm / (adc.z_in_ohm + elec.z_source_ohm),
    }
    return d
