# Instrument budget (assumed until T1-T6)

## 1. Source-impedance loading

| Z_source | Z_in=1 MOhm (ADS1256) | Z_in=1 GOhm (ADS1299) |
|---:|---:|---:|
| 1 kOhm | 0.9990 (0.10% loss) | 1.0000 (0.000100% loss) |
| 10 kOhm | 0.9901 (0.99% loss) | 1.0000 (0.001000% loss) |
| 100 kOhm | 0.9091 (9.09% loss) | 0.9999 (0.009999% loss) |
| 1000 kOhm | 0.5000 (50.00% loss) | 0.9990 (0.099900% loss) |

## 2. Noise floors in 0.01-0.1 Hz

| Source | Thermal noise | ADC noise (10 SPS, PGA=8) |
|---:|---:|---:|
| 1 kOhm | 0.0012 uV RMS | 0.106 uV RMS |
| 10 kOhm | 0.0039 uV RMS | 0.106 uV RMS |
| 100 kOhm | 0.0122 uV RMS | 0.106 uV RMS |
| 1000 kOhm | 0.0386 uV RMS | 0.106 uV RMS |

Interpretation: for source impedances up to ~100 kOhm, thermal and ADC
noise are far below the electrode flicker/drift. The interface, not the
ADC, sets the noise floor.

## 3. Linear drift is removed by the band-pass

48 h ramp at 1 mV/h -> band-passed RMS = 0.000 uV
20 uV sine at 0.03 Hz -> band-passed RMS = 14.14 uV (should be ~14.1)

## 4. Statistical budget

- tau_s=0.5 h, T=24 h -> N_eff ~ 24.0 independent structural states
- tau_s=0.5 h, T=48 h -> N_eff ~ 48.0 independent structural states
- tau_s=1.0 h, T=24 h -> N_eff ~ 12.0 independent structural states
- tau_s=1.0 h, T=48 h -> N_eff ~ 24.0 independent structural states
- tau_s=2.0 h, T=24 h -> N_eff ~ 6.0 independent structural states
- tau_s=2.0 h, T=48 h -> N_eff ~ 12.0 independent structural states
- tau_s=4.0 h, T=24 h -> N_eff ~ 3.0 independent structural states
- tau_s=4.0 h, T=48 h -> N_eff ~ 6.0 independent structural states

Spontaneous fluctuations give only ~6-24 independent samples in 24-48 h;
driven perturbations (periodic food switching) are the way to buy power.

## 5. What the ADC buys

- PGA= 1: LSB=0.2980 uV, FS=+/-2500.000 mV, noise=0.339 uV RMS
- PGA= 2: LSB=0.1490 uV, FS=+/-1250.000 mV, noise=0.214 uV RMS
- PGA= 4: LSB=0.0745 uV, FS=+/-625.000 mV, noise=0.138 uV RMS
- PGA= 8: LSB=0.0373 uV, FS=+/-312.500 mV, noise=0.106 uV RMS
- PGA=16: LSB=0.0186 uV, FS=+/-156.250 mV, noise=0.082 uV RMS
- PGA=32: LSB=0.0093 uV, FS=+/-78.125 mV, noise=0.061 uV RMS
- PGA=64: LSB=0.0047 uV, FS=+/-39.062 mV, noise=0.061 uV RMS

24 bits is not the binding constraint; electrode stability and input
impedance are. PGA=8 gives +/-312.5 mV and 0.106 uV RMS at 10 SPS.
