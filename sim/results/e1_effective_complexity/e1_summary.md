# E1 — effective-complexity calibration (synthetic, known truth)

Evidence label: **computed (model-internal)**. 48 h, 10 s frames, 20 seeds/system; `known_rank` = structure modes + one electrical noise mode.

| system | known modes | known rank | POD PR | CCA rank | energy 95% | N_eff | BIC p/q/quad | lin index | lin p | lin power | drift | drift p | drift power |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| kmode2 | 2 | 3 | 2.79 | 1 | 3 | 21.4 |  |  |  |  |  |  |  |
| kmode4 | 4 | 5 | 4.70 | 1 | 5 | 19.0 |  |  |  |  |  |  |  |
| kmode8 | 8 | 9 | 8.64 | 3 | 9 | 17.9 |  |  |  |  |  |  |  |
| nonlinear | 1 | 2 | 1.89 | 1 | 2 | 18.3 | 4/1/0.55 | 0.1281 | 0.032 | 0.55 | 0.91 | 0.391 | 0.10 |
| nonstationary | 1 | 2 | 1.90 | 0 | 2 | 19.3 | 4/1/0.00 | -0.0098 | 0.597 | 0.00 | 1.88 | 0.069 | 0.40 |
| s0 | 1 | 2 | 1.90 | 0 | 2 | 15.6 | 4/1/0.00 | -0.0016 | 0.435 | 0.00 | 0.55 | 0.599 | 0.05 |

Pre-registered: alpha = 0.05; 30 phase-randomised surrogates; PR = participation ratio (total variance dimension); CCA rank = shared modes from one electrical channel (conservative); lin/drift power = fraction of 20 seeds with p < 0.05; BIC q = 1 is an oversampling artifact, not a lag estimate; BIC p in {1,2,4}, q in {1,4,16,60}.
