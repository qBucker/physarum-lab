# Data inventory

All raw bench acquisitions in `data/` are tracked with Git LFS. After cloning:

```bash
git lfs install
git lfs pull
```

## Bench runs (measured)

| directory | content | size | status |
|---|---|---:|---|
| `data/bench_T1/` | 300 s shorted input, gain 24 | 9.3 MB | PASS: 0.13 uV RMS |
| `data/bench_T2/` | 120 s internal test signal | 3.9 MB | PASS: 3.742 mV pp, 0.2% low |
| `data/bench_T6/` | 600 s shorted input | 19 MB | PASS: 0.169% sequence gaps |
| `data/bench_T6_soak2h/` | 2 h soak over usbipd/WSL | 217 MB | FAIL overall (2.107% gaps); transport attribution evidence |
| `data/bench_win_uart_30m/` | 30 min Windows native COM | 56 MB | PASS: 0.0031% gaps |
| `data/win_uart_partial_2026-11-12/` | 8 min exploratory Windows COM | 12 MB | exploratory; not formal evidence |

Every formal run directory contains `meta.json`, `ANALYSIS.md` where
applicable, and `SHA256SUMS`. The sequence-gap and noise analyses are in the
per-run `ANALYSIS.md`; the scripts that regenerate them are in `host/`.

`data/bench-log.md` is an internal run log and is not published.

## Computed simulation evidence

| directory | content |
|---|---|
| `sim/results/S0-SUMMARY.md` | S0 detectability summary |
| `sim/results/s0_final/` | S0 main grid (computed) |
| `sim/results/s0_design_spont/`, `s0_design_v4/` | S0 design sweeps (computed) |
| `sim/results/r1_latent_recovery/`, `r1_clean_control/` | R1 latent-pipeline recovery test (computed) |
| `sim/results/e1_effective_complexity/` | E1 effective-complexity calibration (computed) |
| `sim/results/s1_network/` | S1 high-dimensional/nonlinear testbed (computed); S1-L2 beats direct linear detectors |
| `sim/results/s1b_direct_baseline/` | S1b direct nonlinear baseline (computed); verdict: quadratic lagged features explain the gain, no latent-representation advantage |
| `sim/results/instrument_budget.md` | static instrument budget (computed, assumed parameters) |

Pilot, superseded, and internal simulation outputs are excluded from the
public repository (`sim/results/_*/`).

## Documents

- `docs/modeling-2026-11-14/` — modeling methods and tools report (Chinese
  HTML with figures), CC BY 4.0.
- `docs/physarum-lab-phase0-2026-11-07.pdf` and
  `docs/project-2026-11-07.html` are internal phase-0 reports and are not
  published. Use the top-level README and `protocols/` instead.

## Third-party material

`vendor/` is not redistributed. It contains vendor firmware (MIT) and vendor
documentation for the BCIkit M1 / ADS1256 hardware; obtain them from the
vendor.
