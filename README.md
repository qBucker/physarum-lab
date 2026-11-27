# physarum-lab

Open instrument, protocol, and analysis stack for measuring
**structure–electrical coupling in *Physarum polycephalum* networks**.

This is a **phase-0 engineering record**, not a biological result yet. The
current goal is a signal chain that can record electrodes and network geometry
together for 24–48 h with auditable data:

```
Physarum → electrodes → BCIkit M1 (ADS1299, 8 ch, 24 bit)
        → ESP32-DevKitC V4 → USB → laptop
                              ↑
                 time-lapse camera + start/stop clock card
```

Detailed Chinese notes and measurement records: [README.zh.md](README.zh.md).

## Status (2026-11-27)

| item | result | label |
|---|---|---|
| T1 shorted input, 300 s | 0.13 µV RMS (σ ≈ 6 counts), gain 24 | measured, PASS |
| T1 sequence gaps | 0.80% over the run | measured |
| T2 internal test signal | 3.742 mV pp; ±1.871 vs ±1.875 nominal (0.2% low) | measured, PASS |
| T2 period | 256 samples; nominal 0.9766 Hz at 250 SPS | measured |
| T2 channel agreement | < 0.3% across 8 channels | measured, PASS |
| T6 600 s, shorted | 0.169% sequence gaps; 248.99 SPS sample clock | measured, PASS |
| 2 h soak over usbipd/WSL | 2.107% gaps overall, 1.566% steady | measured, FAIL for this transport |
| 30 min Windows native COM | 0.0031% gaps (14 samples in 445,637) | measured, PASS |
| 2 h Windows native COM, streaming recorder | 0.00258% gaps (46 samples in 1,784,268) | measured, PASS |
| 48 h Windows native COM | 0.00234% visible gaps (1,003 samples); 0.00833% by device-frame reconciliation | measured, PASS |
| T3–T5 (electrode/agar drift, differential) | pending | — |
| First 9 plates | not started | — |

The 2 h soak failure is **attributed to the host transport, not to the
ADS1299 or the ESP32 firmware**: device counters show
`transport_drop = 0`, `queue_overrun = 0`, `spi_error = 0`, while the host
received 37,433 fewer frames (2.10%). The same board over a Windows native
COM port lost 0.0031% in 30 min, 0.00258% in 2 h with the streaming
recorder, and 0.00234% in 48 h (0.00833% under the more conservative
device-frame reconciliation), 500–680× less than the usbipd/WSL path. The
streaming recorder keeps constant memory (RSS 21–22 MB) over the full 48 h.

A known wiring constraint: the 2.048 MHz clock return path needs a ground
return; twisting GND and CLK is required. A single ground produced
intermittent register read-back failures (`CONFIG1 expected 0x46 actual 0x06`).

## Repository map

| path | content |
|---|---|
| `host/` | recorders and analysis: BCIKit UART, WiFi native frames, bench tests; `live_rig.py` live plate/electrode monitor |
| `run_scripts/` | Windows run helpers: soak watchdog (stall + sequence-gap alerts) |
| `protocols/` | bench tests T1–T7 and first biological run |
| `firmware/` | ADS1256 / ADS1115 logger sketches (fallback path; hardware not purchased) |
| `templates/` | metadata and prediction-card templates |
| `data/` | measured bench acquisitions (Git LFS) and per-run analysis |
| `sim/` | S0/R1/E1/S1/S1b digital-twin and testbed code, plus computed evidence |
| `docs/modeling-2026-11-14/` | modeling methods and tools report (Chinese HTML) |
| `BOM-from-zero.md` | minimum hardware list and wiring |
| `DATA.md` | data inventory, LFS instructions, evidence status |
| `SANITIZATION.md` | publication-time metadata/path sanitization ledger |

## Data and evidence

Raw acquisitions are tracked with **Git LFS**:

```bash
git lfs install
git lfs pull
```

Each formal run directory contains `meta.json`, an `ANALYSIS.md` where
applicable, and `SHA256SUMS`. Raw measurement bytes are never rewritten; the
publication-time metadata sanitization is recorded in
[SANITIZATION.md](SANITIZATION.md).

The internal run log, the third-party `vendor/` tree, the internal phase-0
report, and pilot/superseded simulation outputs are not published. See
[DATA.md](DATA.md).

## Simulations (computed, model-internal)

| module | question | result |
|---|---|---|
| S0 | can a structure–electrical coupling be detected above instrument noise? | ADC noise is not the bottleneck; electrode 1/f and input impedance are. A drive period ≳ 4 × structural time is required; 48 h at a 2 h structural time is underpowered at realistic coupling. |
| R1 | does a delay-embedded latent pipeline beat direct lagged correlation? | No gain at realistic coupling; direct lagged cross-correlation/CCM is the primary detector. The latent model only works near deterministic coupling. |
| E1 | how complex a model does the data support? | POD participation ratio recovers known dimension; nonlinearity test power 0.55; stationarity test power 0.40; N_eff ≈ 16 over 48 h. Start with a 2–4 parameter lagged linear model. |
| S1 / S1b | Does geometric POD plus a nonlinear latent layer beat direct detectors on a high-dimensional nonlinear network? | At rho = 0.9 quadratic, S1-L2 (POD/PCA) 0.77 vs direct linear 0.13/0.23. The direct nonlinear baseline DQ-A (16 raw electrodes × 8 region means, same quadratic library) reaches 0.93 (matched 0.967 vs 0.867); all detectors are 0.0 in the linear cell. S1b verdict: the gain is the quadratic lagged features, not the latent POD/PCA representation. R1's linear-latent no-gain result stands. |

S1 uses a stationary log-homeostatic Tero–Kobayashi network, a 24 × 20 camera
POD, 8/16/32-electrode lead fields, and a partial delayed-gain statistic at a
600 s lag. The latent detectors use the pre-registered lag; the fixed-lag
direct baselines at the same lag are D1f/D2f = 0.13/0.33 at rho = 0.9, still
below L2 = 0.77. S1b then ran the missing control: the direct nonlinear
baseline DQ-A (16 raw electrode channels × 8 region means, same quadratic
library and estimator) reaches 0.93 (matched 0.967) vs S1-L2 0.77 (0.867);
all detectors are 0.0 in the linear cell, so the comparison is specific to
the quadratic cell. Verdict: the gain is the quadratic lagged features, not
the POD/PCA latent representation. Results: `sim/results/s1_network/` and
`sim/results/s1b_direct_baseline/s1b_summary.md`. It is a testbed, not a
biological claim.

## Quick start

```bash
# instrument budget (computed)
cd sim && python3 instrument_budget.py

# bench-test analysis
python3 host/bench_test.py data/bench_T1/samples.csv --label T1 --max-noise-uv 5

# S1 testbed (after cloning; ~30 min for the full grid)
cd sim && OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    python3 s1_network_testbed.py --grid all --outdir results/s1_network

# S1b direct nonlinear baseline (~18 min)
cd sim && OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    python3 s1b_direct_baseline.py --grid all --outdir results/s1b_direct_baseline
```

Requirements: Python 3.11+, `numpy`, `scipy`, `matplotlib`, and `pyserial`
for acquisition.

## License and citation

- Code: MIT License ([LICENSE](LICENSE)).
- Data, computed evidence, and documentation: CC BY 4.0
  ([DATA-LICENSE.md](DATA-LICENSE.md)).

Cite this repository and the commit hash used. A Zenodo DOI will be added when
the dataset is archived.

## Contact

Open an issue on GitHub. The public identity for this repository is the
GitHub account `qBucker`.
