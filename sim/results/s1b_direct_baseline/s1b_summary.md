# S1b — direct nonlinear baseline

Evidence label: **computed (model-internal)**. `rho` is a model parameter, not a biological measurement.

Pre-registered: see the module docstring and `run_meta.json`; alpha = 0.05, surrogates = 50, lag = 600 s.

## Primary cell (rho = 0.9, quadratic, 100 uV, camera 0.03)

| detector | power (nominal) | power (matched) | linear-cell power | FPR |
|---|---:|---:|---:|---:|
| S1L2 | 0.767 | 0.867 | 0.000 | 0.017 |
| DQA | 0.933 | 0.967 | 0.000 | 0.000 |
| DQC | 0.900 | 0.800 | 0.000 | 0.033 |
| DQD | 0.900 | 0.967 | 0.000 | 0.000 |

## Decision

- Status: **QUADRATIC FEATURES EXPLAIN THE GAIN: the direct nonlinear baseline DQ-A matches or exceeds S1-L2; no evidence for a latent-representation advantage**
- p(S1-L2) = 0.867; p(DQ-A) = 0.967; difference = -0.100
- Matched thresholds used: True
- Paired S1-L2 vs DQ-A: {"a": "s1l2", "b": "dqa", "s1l2_only": 1, "dqa_only": 6, "both": 22, "neither": 1, "sign_test_p": 0.125}
- S1 reference check: {"available": true, "n_paired": 120, "missing": 0, "max_abs_p_diff": 0.0, "s1_reference_note": "S1-L2 in S1b is recomputed with the same seed and surrogate stream; small differences can arise from the ARPACK POD starting vector."}

## Secondary grid (descriptive)

| cell | n | S1-L2 | DQ-A | DQ-C | DQ-D |
|---|---:|---:|---:|---:|---:|
| quadratic|0.0|100uV|cam0.10 | 20 | 0.000 | 0.000 | 0.050 | 0.000 |
| quadratic|0.0|20uV|cam0.03 | 20 | 0.000 | 0.000 | 0.050 | 0.000 |
| quadratic|0.9|100uV|cam0.10 | 20 | 0.950 | 0.850 | 0.850 | 0.850 |
| quadratic|0.9|20uV|cam0.03 | 20 | 0.800 | 0.900 | 0.900 | 0.850 |

## Notes

- DQ-A is the pre-registered direct nonlinear baseline: 16 raw electrode channels x 8 region means (4 x 2 grid), same quadratic library and estimator as S1-L2.
- DQ-C and DQ-D isolate the electrical PCA and the geometry POD respectively.
- The 600 s lag is pre-registered; all detectors use the same lag.
- The testbed is not a biological claim; S1b does not replace the four experimental controls.
