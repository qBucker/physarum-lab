# T2 — internal test signal (BCIkit M1 / ADS1299)

Run: 2026-11-11, 120 s, `mode test`, 250 SPS, 1 board, gain 24.
Command: `host/bcikit_openbci.py --port /dev/ttyUSB0 --mode test --duration 120 --outdir data/bench_T2`

## Result (measured)

| Item | Value | Expected | Verdict |
|---|---:|---:|---|
| Frames | 28,793 | — | — |
| Amplitude (peak-to-peak) | 167,397 counts | 167,772 counts | 0.2 % low |
| Amplitude (volts) | 3.742 mV (±1.871 mV) | 3.750 mV (±1.875 mV) | PASS |
| Period | 256 samples | 256 samples | PASS |
| Frequency | 0.9766 Hz | 0.9766 Hz | PASS |
| Channel spread | < 0.3 % | — | PASS |
| Hidden high-pass | none (0.5 s plateau flat) | — | PASS |

LSB at gain 24: 4.5 V / (24 × 2^23) = 2.235e-8 V/count.
2 × 83,886 counts × 2.235e-8 = 3.750 mV peak-to-peak.

## Time base

Use the **ADS1299 sample counter**, not host arrival timestamps. The
effective UART rate was 242.3 SPS by sample number and 239.3 SPS by host
time; over 120 s this distorts a host-time frequency estimate (1.08 Hz)
although the device period is exactly 256 samples.

## Known anomaly

About one quarter of the high phases are stretched (longest 492 samples,
i.e. nearly two periods). There are no missing samples and no exact
duplicate samples inside these runs (max identical run = 5 samples), so
this is a property of the test signal / firmware DRDY handling, not a
transport artefact. It does not affect the gain/amplitude calibration,
but the internal test signal should not be used as a timing reference.

## Files

- `raw.bin` — raw UART bytes after `start`
- `samples.csv` — host time, sample number, 8 raw channels
- `meta.json` — configuration and firmware status snapshot
- `waveform.png` — CH1, three cycles, device sample clock
- `SHA256SUMS`
