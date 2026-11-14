# S1 — high-dimensional / nonlinear network testbed

Evidence label: **computed (model-internal)**. `rho` is a model parameter, not a biological measurement; no experimental claim.

Pre-registered design: see the module docstring and `run_meta.json`; alpha = 0.05, lag = 600 s, tolerance ±120 s, surrogates = 50.

## Primary grid — detection rate

| coupling | rho | n | D1 | D2 | D1f | D2f | L1 | L2 | L1 rev | L2 rev |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| linear | 0.0 | 30 | 0.000 | 0.000 | 0.000 | 0.067 | 0.033 | 0.033 | 0.067 | 0.100 |
| linear | 0.5 | 30 | 0.067 | 0.333 | 0.067 | 0.433 | 0.167 | 0.000 | 0.067 | 0.033 |
| linear | 0.7 | 30 | 0.167 | 0.833 | 0.167 | 0.933 | 0.667 | 0.000 | 0.100 | 0.000 |
| linear | 0.9 | 30 | 0.633 | 1.000 | 0.733 | 1.000 | 1.000 | 0.000 | 0.033 | 0.033 |
| quadratic | 0.0 | 30 | 0.067 | 0.000 | 0.067 | 0.000 | 0.000 | 0.000 | 0.033 | 0.067 |
| quadratic | 0.5 | 30 | 0.133 | 0.267 | 0.133 | 0.267 | 0.233 | 0.200 | 0.000 | 0.033 |
| quadratic | 0.7 | 30 | 0.233 | 0.233 | 0.233 | 0.400 | 0.467 | 0.400 | 0.033 | 0.100 |
| quadratic | 0.9 | 30 | 0.133 | 0.233 | 0.133 | 0.333 | 0.633 | 0.767 | 0.033 | 0.100 |

## Lag and direction among detected runs

| coupling | rho | detector | detected | lag recovered | median lag (s) | direction correct |
|---|---:|---|---:|---:|---:|---:|
| linear | 0.0 | D2F | 2/30 | 1.000 | 600 | 1.000 |
| linear | 0.0 | L1 | 1/30 | 1.000 | 600 | 1.000 |
| linear | 0.0 | L2 | 1/30 | 1.000 | 600 | 1.000 |
| linear | 0.5 | D1 | 2/30 | 0.500 | 325 | 0.500 |
| linear | 0.5 | D2 | 10/30 | 0.400 | 590 | 0.900 |
| linear | 0.5 | D1F | 2/30 | 1.000 | 600 | 1.000 |
| linear | 0.5 | D2F | 13/30 | 1.000 | 600 | 1.000 |
| linear | 0.5 | L1 | 5/30 | 1.000 | 600 | 1.000 |
| linear | 0.7 | D1 | 5/30 | 0.200 | 600 | 1.000 |
| linear | 0.7 | D2 | 25/30 | 0.880 | 600 | 0.920 |
| linear | 0.7 | D1F | 5/30 | 1.000 | 600 | 1.000 |
| linear | 0.7 | D2F | 28/30 | 1.000 | 600 | 1.000 |
| linear | 0.7 | L1 | 20/30 | 1.000 | 600 | 1.000 |
| linear | 0.9 | D1 | 19/30 | 0.842 | 600 | 0.947 |
| linear | 0.9 | D2 | 30/30 | 1.000 | 600 | 1.000 |
| linear | 0.9 | D1F | 22/30 | 1.000 | 600 | 1.000 |
| linear | 0.9 | D2F | 30/30 | 1.000 | 600 | 1.000 |
| linear | 0.9 | L1 | 30/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.0 | D1 | 2/30 | 0.000 | 455 | 0.500 |
| quadratic | 0.0 | D1F | 2/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.5 | D1 | 4/30 | 0.250 | 1675 | 1.000 |
| quadratic | 0.5 | D2 | 8/30 | 0.750 | 610 | 1.000 |
| quadratic | 0.5 | D1F | 4/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.5 | D2F | 8/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.5 | L1 | 7/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.5 | L2 | 6/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.7 | D1 | 7/30 | 0.286 | 360 | 0.571 |
| quadratic | 0.7 | D2 | 7/30 | 0.857 | 590 | 0.857 |
| quadratic | 0.7 | D1F | 7/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.7 | D2F | 12/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.7 | L1 | 14/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.7 | L2 | 12/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.9 | D1 | 4/30 | 0.750 | 595 | 0.750 |
| quadratic | 0.9 | D2 | 7/30 | 0.857 | 610 | 1.000 |
| quadratic | 0.9 | D1F | 4/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.9 | D2F | 10/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.9 | L1 | 19/30 | 1.000 | 600 | 1.000 |
| quadratic | 0.9 | L2 | 23/30 | 1.000 | 600 | 1.000 |

## Empirical false-positive rate at rho = 0

| detector | detected / n | FPR | threshold (95th pct) |
|---|---:|---:|---:|
| D1 | 2/60 | 0.033 | 0.2647 |
| D2 | 0/60 | 0.000 | 0.6222 |
| D1F | 2/60 | 0.033 | 0.2592 |
| D2F | 2/60 | 0.033 | 0.5993 |
| L1 | 1/60 | 0.017 | 0.03319 |
| L2 | 1/60 | 0.017 | 0.08838 |

Matched-threshold power (used only if FPR outside [0.02, 0.10]):

| cell | D1 | D2 | L1 | L2 |
|---|---:|---:|---:|---:|
| linear|0.0 | 0.033 | 0.100 | 0.067 | 0.100 |
| linear|0.5 | 0.133 | 0.500 | 0.300 | 0.000 |
| linear|0.7 | 0.200 | 1.000 | 0.833 | 0.000 |
| linear|0.9 | 0.733 | 1.000 | 1.000 | 0.000 |
| quadratic|0.0 | 0.067 | 0.000 | 0.033 | 0.000 |
| quadratic|0.5 | 0.233 | 0.467 | 0.467 | 0.167 |
| quadratic|0.7 | 0.300 | 0.467 | 0.667 | 0.500 |
| quadratic|0.9 | 0.300 | 0.567 | 0.800 | 0.867 |

## Secondary grid — K sweep (descriptive)

| cell | n | D1 | D2 | L1 | L2 |
|---|---:|---:|---:|---:|---:|
| quadratic|0.0|K32 | 20 | 0.000 | 0.000 | 0.050 | 0.000 |
| quadratic|0.0|K8 | 20 | 0.000 | 0.000 | 0.000 | 0.050 |
| quadratic|0.7|K32 | 20 | 0.000 | 0.250 | 0.450 | 0.600 |
| quadratic|0.7|K8 | 20 | 0.100 | 0.200 | 0.250 | 0.450 |

## Positive controls (clean, rho=1; diagnostic)

| cell | n | D1 | D2 | L1 | L2 |
|---|---:|---:|---:|---:|---:|
| linear|1.0 | 10 | 0.800 | 1.000 | 1.000 | 0.000 |
| quadratic|1.0 | 10 | 0.300 | 0.300 | 0.700 | 0.800 |

## Pre-registered verdict

- Status: **LATENT ADDS VALUE: max latent power exceeds best direct detector by >= 0.20 with acceptable direction and L2 specificity**
- Informative rho: 0.9
- Powers: {"d1": 0.13333333333333333, "d2": 0.23333333333333334, "l1": 0.6333333333333333, "l2": 0.7666666666666667}
- Best direct = 0.233; best latent = 0.767 (L2)
- Lag recovered (best latent) = 1.000; direction correct = 1.000
- L2 linear-cell power = 0.000 (specific = True)

## Notes

- Positive-control and secondary-grid runs, when present in `s1_results.json`, are separate record blocks; the verdict above uses the primary grid only.
- The truth model is a stationary log-homeostatic TK variant, a testbed device, not a biological claim.
- The 100 uV carrier makes instrument noise subdominant; the 20 uV detectability question belongs to S0.
- POD uses the training segment only; the 90% variance rule is capped at 8 modes.
- The camera sees D linearly; the quadratic coupling is invisible to linear statistics by construction.
- `rho` is a model parameter; S1 cannot replace the four experimental controls.
