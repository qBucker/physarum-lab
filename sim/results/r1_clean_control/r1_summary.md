# R1 — latent-pipeline recovery in the S0 digital twin

**Clean control (post-hoc diagnostic): no flicker, drift, or structural observation noise.**

Evidence label: **computed (model-internal)**. `rho` is a model parameter, not a biological measurement; no experimental claim.

| rho | n | latent power | latent reverse power | baseline power | direction correct | lag ±120 s | lag median | baseline lag ±120 s | baseline lag median | r at lag median | realized r median |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 30 | 0.000 | 0.067 | 0.033 | nan | nan | nan | 0.000 | -1800 | nan | nan |
| 0.2 | 30 | 0.033 | 0.000 | 0.267 | 1.000 | 1.000 | 590 | 0.500 | 590 | -0.153 | -0.152 |
| 0.3 | 30 | 0.067 | 0.067 | 0.367 | 1.000 | 1.000 | 590 | 0.909 | 600 | 0.209 | 0.208 |
| 1.0 | 30 | 1.000 | 0.000 | 1.000 | 1.000 | 1.000 | 590 | 1.000 | 600 | 0.999 | 1.000 |

Pre-registered tolerance: |lag − 600 s| ≤ 120 s; alpha = 0.05; phase-randomised surrogates; n per rho as listed in the table.
