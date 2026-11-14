# S0 detectability — preliminary results

All numbers are **computed inside the model**; instrument parameters are
`assumed` until T1–T6. Detection = p < 0.05 vs 200 surrogates.

- signal model = am
- fs = 1.0 Hz, frame = 10.0 s, lag = 600.0 s, drive period = 7200.0 s, signal = 20.0 uV
- drift = 1.0 mV/h, source impedance = 10000 Ohm

| mode | rho | flicker (uV) | duration (h) | tau (h) | period (h) | power | median p | lag/response |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| spontaneous | 0.00 | 1 | 24 | 2.0 | — | 0.00 | 0.530 | lag 315 s (err 1185 s) |
| spontaneous | 0.00 | 1 | 48 | 2.0 | — | 0.03 | 0.428 | lag 10 s (err 890 s) |
| spontaneous | 0.00 | 10 | 24 | 2.0 | — | 0.03 | 0.522 | lag 180 s (err 1105 s) |
| spontaneous | 0.00 | 10 | 48 | 2.0 | — | 0.03 | 0.567 | lag 365 s (err 1125 s) |
| spontaneous | 0.00 | 30 | 24 | 2.0 | — | 0.05 | 0.542 | lag -530 s (err 910 s) |
| spontaneous | 0.00 | 30 | 48 | 2.0 | — | 0.07 | 0.530 | lag 235 s (err 920 s) |
| spontaneous | 0.10 | 1 | 24 | 2.0 | — | 0.15 | 0.450 | lag -55 s (err 520 s) |
| spontaneous | 0.10 | 1 | 48 | 2.0 | — | 0.20 | 0.408 | lag 275 s (err 705 s) |
| spontaneous | 0.10 | 10 | 24 | 2.0 | — | 0.07 | 0.313 | lag 295 s (err 885 s) |
| spontaneous | 0.10 | 10 | 48 | 2.0 | — | 0.07 | 0.346 | lag -25 s (err 910 s) |
| spontaneous | 0.10 | 30 | 24 | 2.0 | — | 0.05 | 0.383 | lag -55 s (err 605 s) |
| spontaneous | 0.10 | 30 | 48 | 2.0 | — | 0.07 | 0.368 | lag 280 s (err 510 s) |
| spontaneous | 0.20 | 1 | 24 | 2.0 | — | 0.17 | 0.306 | lag 565 s (err 515 s) |
| spontaneous | 0.20 | 1 | 48 | 2.0 | — | 0.20 | 0.246 | lag 545 s (err 400 s) |
| spontaneous | 0.20 | 10 | 24 | 2.0 | — | 0.17 | 0.234 | lag 595 s (err 675 s) |
| spontaneous | 0.20 | 10 | 48 | 2.0 | — | 0.25 | 0.119 | lag 585 s (err 365 s) |
| spontaneous | 0.20 | 30 | 24 | 2.0 | — | 0.15 | 0.264 | lag -305 s (err 830 s) |
| spontaneous | 0.20 | 30 | 48 | 2.0 | — | 0.33 | 0.189 | lag 580 s (err 310 s) |
| spontaneous | 0.30 | 1 | 24 | 2.0 | — | 0.17 | 0.182 | lag 600 s (err 240 s) |
| spontaneous | 0.30 | 1 | 48 | 2.0 | — | 0.38 | 0.087 | lag 590 s (err 225 s) |
| spontaneous | 0.30 | 10 | 24 | 2.0 | — | 0.12 | 0.189 | lag 590 s (err 335 s) |
| spontaneous | 0.30 | 10 | 48 | 2.0 | — | 0.57 | 0.032 | lag 605 s (err 95 s) |
| spontaneous | 0.30 | 30 | 24 | 2.0 | — | 0.20 | 0.182 | lag 455 s (err 325 s) |
| spontaneous | 0.30 | 30 | 48 | 2.0 | — | 0.45 | 0.065 | lag 595 s (err 440 s) |
| driven | 0.00 | 1 | 24 | 2.0 | 2.0 | 0.03 | 0.570 | resp 2.2 uV |
| driven | 0.00 | 1 | 48 | 2.0 | 2.0 | 0.00 | 0.694 | resp 1.3 uV |
| driven | 0.00 | 10 | 24 | 2.0 | 2.0 | 0.00 | 0.540 | resp 2.3 uV |
| driven | 0.00 | 10 | 48 | 2.0 | 2.0 | 0.00 | 0.669 | resp 1.4 uV |
| driven | 0.00 | 30 | 24 | 2.0 | 2.0 | 0.00 | 0.602 | resp 1.7 uV |
| driven | 0.00 | 30 | 48 | 2.0 | 2.0 | 0.00 | 0.669 | resp 1.1 uV |
| driven | 0.10 | 1 | 24 | 2.0 | 2.0 | 0.00 | 0.654 | resp 1.9 uV |
| driven | 0.10 | 1 | 48 | 2.0 | 2.0 | 0.03 | 0.495 | resp 2.0 uV |
| driven | 0.10 | 10 | 24 | 2.0 | 2.0 | 0.05 | 0.614 | resp 2.4 uV |
| driven | 0.10 | 10 | 48 | 2.0 | 2.0 | 0.03 | 0.515 | resp 2.1 uV |
| driven | 0.10 | 30 | 24 | 2.0 | 2.0 | 0.03 | 0.575 | resp 1.7 uV |
| driven | 0.10 | 30 | 48 | 2.0 | 2.0 | 0.00 | 0.694 | resp 1.2 uV |
| driven | 0.20 | 1 | 24 | 2.0 | 2.0 | 0.00 | 0.644 | resp 2.4 uV |
| driven | 0.20 | 1 | 48 | 2.0 | 2.0 | 0.07 | 0.555 | resp 1.7 uV |
| driven | 0.20 | 10 | 24 | 2.0 | 2.0 | 0.00 | 0.570 | resp 2.6 uV |
| driven | 0.20 | 10 | 48 | 2.0 | 2.0 | 0.10 | 0.652 | resp 1.8 uV |
| driven | 0.20 | 30 | 24 | 2.0 | 2.0 | 0.00 | 0.515 | resp 2.0 uV |
| driven | 0.20 | 30 | 48 | 2.0 | 2.0 | 0.05 | 0.515 | resp 1.3 uV |
| driven | 0.30 | 1 | 24 | 2.0 | 2.0 | 0.00 | 0.478 | resp 2.4 uV |
| driven | 0.30 | 1 | 48 | 2.0 | 2.0 | 0.03 | 0.331 | resp 2.5 uV |
| driven | 0.30 | 10 | 24 | 2.0 | 2.0 | 0.03 | 0.545 | resp 2.2 uV |
| driven | 0.30 | 10 | 48 | 2.0 | 2.0 | 0.00 | 0.458 | resp 1.9 uV |
| driven | 0.30 | 30 | 24 | 2.0 | 2.0 | 0.05 | 0.450 | resp 2.1 uV |
| driven | 0.30 | 30 | 48 | 2.0 | 2.0 | 0.03 | 0.532 | resp 1.3 uV |

## Implied requirements

The binding constraints are the number of independent structural
states and the structural observation noise, not the ADC.  In-band
electrode flicker matters less because the structural signal is slow
and averages over fast flicker.
Read the minimum rho with power >= 0.8 at the highest tolerable flicker.
If no cell reaches 0.8, the experiment needs either longer duration,
driven perturbations, or a faster/less noisy structural observable.
