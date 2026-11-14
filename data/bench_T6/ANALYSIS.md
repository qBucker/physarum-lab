# T6 — time base and drop audit (BCIkit M1 / ADS1299)

Run: 2026-11-12 20:04:16–20:14:16 CST, 600 s, `mode short`, 250 SPS nominal, 1 board, gain 24.
Command: `host/bcikit_openbci.py --port /dev/ttyUSB0 --mode short --duration 600 --outdir data/bench_T6 --label T6`

## Result (measured)

| Item | Value | Criterion | Verdict |
|---|---:|---:|---|
| Frames | 149,144 | — | — |
| Host duration (first→last frame) | 599.997 s | — | — |
| Sample-number span | 149,395 | — | — |
| Gap events | 65 | — | — |
| Missing samples | 252 | — | — |
| Gap fraction | **0.168 %** | < 2 % | PASS |
| Max step | 13 samples (12 missing) | — | — |
| Zero/duplicate steps | 0 | monotonic | PASS |
| `fs_effective` (sample clock) | **248.993 SPS** | recorded | PASS |
| `fs_effective` (host clock) | **248.574 SPS** | recorded | PASS |
| Sample–host clock difference | 0.419 SPS = 0.168 % | ≈ gap fraction | PASS |
| Host-clock anchors | photos 20:07:45 / 20:14:30 (time.is, NTP) | recorded | PASS (coarse) |

The sample clock is 0.40 % below the nominal 250 SPS; the host clock is another
0.17 % low, exactly the missing-sample fraction. This is the expected
sample-number/host-time relation and the reason all absolute frequencies must
use `fs_effective`, never the host arrival rate.

## Time base

Use the ADS1299 `sample_number` sequence, not host arrival timestamps. The
UART rate is not the sample clock: frame arrival is bursty and loses samples.
`fs_effective = sample-number span / host duration`; for this run 248.993 SPS.
Cross-run values (T1 246.8, T2 242.3, T6 249.0) vary by more than the gap rate
explains, so 48 h runs require the BCIKit native frames (32-bit sequence +
64-bit DRDY timestamp) instead of OpenBCI UART frames.

## Anomalies (recorded)

1. **Link verify retry on startup.** `mode short` returned
   `WARN ADS verify attempt=1 reg=0x01 expected=0x46 actual=0x06 id=0x3E`;
   the firmware retried and `status` reports `register_verified=yes`,
   `verify_error=0`, `queue_overrun=0`, `transport_drop=0`. This is the known
   GND/CLK harness sensitivity seen on 2026-11-11. Recheck the twisted
   GND+CLK pair before 48 h runs.

2. **Gap rate increases monotonically over the run.** Missing-sample rate per
   100 s bin: 0.048, 0.028, 0.016, 0.104, 0.277, **0.538 %** (0–600 s). A
   cluster of 10 gap events occurs at 530.8–531.9 s. The 10 min total still
   passes the < 2 % criterion, but the trend is a 48 h risk. Next: a 2 h soak
   to see whether the rate saturates; check Windows USB power management and
   usbipd link stability.

3. **Single 8-channel transient at t ≈ 526.4 s.** All channels move together;
   ch1 peak deviation 10,147 counts ≈ 227 µV, duration ≈ 0.2 s. No electrodes
   were connected (`short` mode), so this is a board/PSU/USB event, not
   biological. It does not affect the T6 criteria.

4. **Camera deviation.** The protocol asks for one frame per 10 s; only two
   anchors were taken (20:07:45 and 20:14:30, time.is). Both bracket the
   recording (host 20:04:16–20:14:16), which excludes minute-level clock
   error, but the 13.7 s shutter delay after the last sample means the
   second-level host-clock offset is not resolvable this way.

## Channel noise (0.01–5 Hz, `short` mode)

ch1 0.512, ch2 0.206, ch3 0.069, ch4 0.122, ch5 0.181, ch6 0.179,
ch7 0.051, ch8 0.094 µV RMS. ch1 is dominated by the 526.4 s transient;
excluding it the floor is ≈ 0.05–0.2 µV. Binned drift |value| ≤ 1.0e-3 mV/h
on all channels. Mains ratio after 50 Hz notch: 0.012 (raw 0.077).

## Verdict

PASS on all formal T6 criteria, with anomalies 1–3 flagged for the long-run
work.
