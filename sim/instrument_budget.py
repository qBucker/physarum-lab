#!/usr/bin/env python3
"""Static instrument budget for the Physarum phase-0 chain.

Prints the numbers that decide whether the ADC or the electrode interface is
the bottleneck.  Run:

    python3 instrument_budget.py

All values are computed from the stated assumptions; none are measured yet.
"""
from __future__ import annotations

import numpy as np

from instrument import ADCModel, ElectrodeModel, thermal_noise_uv
from pipeline import bandpass

K_ADC_NOISE_UV = 0.106  # ADS1256, 10 SPS, PGA=8, buffer on, inputs shorted


def main():
    print("# Instrument budget (assumed until T1-T6)\n")
    print("## 1. Source-impedance loading\n")
    print("| Z_source | Z_in=1 MOhm (ADS1256) | Z_in=1 GOhm (ADS1299) |")
    print("|---:|---:|---:|")
    for zs in [1e3, 10e3, 100e3, 1e6]:
        a = 1e6 / (1e6 + zs)
        b = 1e9 / (1e9 + zs)
        print(f"| {zs/1e3:.0f} kOhm | {a:.4f} ({100*(1-a):.2f}% loss) | "
              f"{b:.4f} ({100*(1-b):.6f}% loss) |")

    print("\n## 2. Noise floors in 0.01-0.1 Hz\n")
    bw = 0.09
    print("| Source | Thermal noise | ADC noise (10 SPS, PGA=8) |")
    print("|---:|---:|---:|")
    for zs in [1e3, 10e3, 100e3, 1e6]:
        th = thermal_noise_uv(zs, bw)
        print(f"| {zs/1e3:.0f} kOhm | {th:.4f} uV RMS | {K_ADC_NOISE_UV:.3f} uV RMS |")

    print("\nInterpretation: for source impedances up to ~100 kOhm, thermal and ADC")
    print("noise are far below the electrode flicker/drift. The interface, not the")
    print("ADC, sets the noise floor.")

    print("\n## 3. Linear drift is removed by the band-pass\n")
    fs = 1.0
    dur_h = 48.0
    t = np.arange(0, dur_h * 3600.0, 1.0 / fs)
    ramp = 1.0 * t / 3600.0  # 1 mV/h
    ramp_bp = bandpass(ramp, fs, 0.01, 0.1)
    core = slice(len(t) // 10, -len(t) // 10)
    print(f"48 h ramp at 1 mV/h -> band-passed RMS = "
          f"{np.std(ramp_bp[core])*1e3:.3f} uV")
    sine = 20e-3 * np.sin(2 * np.pi * 0.03 * t)
    sine_bp = bandpass(sine, fs, 0.01, 0.1)
    print(f"20 uV sine at 0.03 Hz -> band-passed RMS = "
          f"{np.std(sine_bp[core])*1e3:.2f} uV (should be ~14.1)")

    print("\n## 4. Statistical budget\n")
    for tau_h in [0.5, 1.0, 2.0, 4.0]:
        for dur_h in [24.0, 48.0]:
            n_eff = dur_h / (2.0 * tau_h)
            print(f"- tau_s={tau_h:.1f} h, T={dur_h:.0f} h -> "
                  f"N_eff ~ {n_eff:.1f} independent structural states")
    print("\nSpontaneous fluctuations give only ~6-24 independent samples in 24-48 h;")
    print("driven perturbations (periodic food switching) are the way to buy power.")

    print("\n## 5. What the ADC buys\n")
    for pga in [1, 2, 4, 8, 16, 32, 64]:
        adc = ADCModel(fs=10.0, pga=float(pga))
        print(f"- PGA={pga:2d}: LSB={adc.lsb_mv*1e3:.4f} uV, "
              f"FS=+/-{adc.full_scale_mv:.3f} mV, noise={adc.rms_noise_uv():.3f} uV RMS")
    print("\n24 bits is not the binding constraint; electrode stability and input")
    print("impedance are. PGA=8 gives +/-312.5 mV and 0.106 uV RMS at 10 SPS.")


if __name__ == "__main__":
    main()
