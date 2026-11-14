# T6 soak (2 h) — long-run time base and drop audit

Run: 2026-11-12 20:47:34–22:47:34 CST, 7200 s, `mode short`, 250 SPS nominal,
1 board, gain 24. Command:

    host/bcikit_openbci.py --port /dev/ttyUSB0 --mode short --duration 7200 \
        --outdir data/bench_T6_soak2h --label T6-soak2h

## Result (measured)

| Item | Value | Criterion | Verdict |
|---|---:|---:|---|
| Frames received | 1,745,347 | — | — |
| Host duration | 7200.0 s | — | — |
| Sample-number span | 1,782,903 | — | — |
| Gap events | 11,347 | — | — |
| Missing samples | 37,557 | — | — |
| Gap fraction | **2.107 %** | < 2 % | **FAIL** (overall) |
| Steady state 40–120 min | **1.566 %** | < 2 % | marginal PASS |
| First 40 min | **3.188 %** | — | transient |
| Zero/duplicate steps | 0 | monotonic | PASS |
| `fs_effective` (sample clock) | 247.626 SPS | recorded | PASS |
| `fs_effective` (host clock) | 242.410 SPS | recorded | PASS |
| Sample–host clock difference | 5.22 SPS = **2.11 %** | ≈ gap fraction | PASS |

The corrected `bench_test.py` denominator is used (see Tool changes below):
`gap_fraction = missing / sample-number span`, not `missing / (span + missing)`.

## Attribution: device healthy, loss is on the host/USB side

Device counters, start status (`meta.json`) vs end status (`device_status_end.txt`):

| Counter | Start | End | Δ over soak |
|---|---:|---:|---:|
| drdy | 237,471 | 2,020,258 | **+1,782,787** |
| frames produced | 237,435 | 2,020,215 | **+1,782,780** |
| sync_error | 5 | 9 | +4 |
| spi_error | 0 | 0 | 0 |
| timeout | 1,912 | 6,308 | +4,396 |
| queue_overrun | 0 | 0 | **0** |
| transport_drop | 4,254 | 4,254 | **0** |
| verify_error | 0 | 0 | 0 |

The device produced 1,782,780 frames and its UART transport reported **zero
drops**. The host received 1,745,347; the difference is **37,433 frames
(2.10 %)**, matching the sequence-derived 37,557. Therefore the loss happens
between the ESP32 UART and the host process — CP2102 / usbipd / WSL tty
buffering — not in the ADS1299, the SPI read, the sample queue, or the
firmware transport write.

The `timeout` counter (+4,396) is consistent with the acquisition loop
occasionally blocking on `Serial.write` when the host path stalls; it did not
overflow the DRDY queue (queue_overrun = 0) and did not stop acquisition.

## Gap structure

- 92.1 % of missing samples are in gaps ≥ 2 samples; 61.6 % in gaps ≥ 4;
  24.7 % in gaps ≥ 8; max single gap **182 samples ≈ 0.73 s**.
- Largest 10 s windows: t ≈ 310 s (782 missing), t ≈ 250 s (702),
  t ≈ 190 s (465), t ≈ 2250 s (793), t ≈ 1380 s (441).
- The USB/IP reset seen in dmesg at 20:56 (t ≈ 506 s) accounts for only
  ~52 missing samples; it is **not** the main cause.
- Loss is bursty transport stalling, not random byte corruption.

## Gap rate per 10 min

```
 0–10  5.032%    40–50  1.481%    80–90   1.532%
10–20  2.693%    50–60  1.307%    90–100  1.556%
20–30  2.766%    60–70  1.549%   100–110  1.586%
30–40  2.192%    70–80  1.774%   110–120  1.670%
```

## Signal floor (short mode, 0.01–5 Hz)

ch1 0.640, ch2 0.546, ch3 0.508, ch4 0.399, ch5 0.454, ch6 0.482,
ch7 0.434, ch8 0.368 µV RMS. Binned drift ≤ 1.0e-5 mV/h on ch1. The board
noise floor remains sub-µV; the soak problem is transport, not analog.

## Verdict

- Overall **FAIL** on the < 2 % gap criterion (2.107 %), driven by the first
  40 min (3.19 %); steady state 40–120 min is **1.57 %** (marginal PASS).
- Device-side counters **exculpate the board**: zero transport drops, zero
  queue overruns, zero SPI errors; produced frames match DRDY counts.
- UART over **usbipd/WSL is not 48 h-grade**. Next: controlled A/B between
  (a) WSL + usbipd, (b) Windows-side UART recorder (native COM, no usbipd),
  (c) BCIKit native frames over WiFi.

## Tool changes

1. `bench_test.py`: `gap_fraction` denominator fixed — `seq_span` already
   contains the missing samples, so the old `seq_span + gap_samples`
   under-reported the fraction (T6 0.168 % → 0.1687 %; this soak 2.063 % →
   2.107 %). No verdict changes at T6; the soak was already over 2 %.
2. `bcikit_openbci.py` captures device status only at configure time. For the
   next run, read `status` again at the end (or add it to the recorder) so the
   device counters are part of the evidence, not a manual follow-up.
