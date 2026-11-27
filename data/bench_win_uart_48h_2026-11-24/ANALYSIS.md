# Windows COM UART — 48 h soak (2026-11-24/26)

Run: 2026-11-24 23:19:10.555–2026-11-26 23:19:11.722 CST
(UTC 15:19:10.555–15:19:11.722), 172,801.17 s requested/achieved,
`mode short`, 250 SPS nominal, 1 board, gain 24, **Windows native COM6**
(`D:\phy\python.exe`, pyserial 3.5), streaming recorder
`host/bcikit_openbci.py` (2026-11-16 diff: 1.5 s post-open delay,
`device_status_start/end`), output on local `C:` (not the WSL 9p share).
`keep_awake.py` (SetThreadExecutionState) and USB selective-suspend-off
were active; a read-only watchdog sampled `raw.bin` growth every 60 s.

## Result (measured)

| Item | Value |
|---|---:|
| Frames received | 42,820,366 |
| Host duration (meta) | 172,801.17 s |
| CSV timestamp span | 172,800.00 s |
| Device DRDY | 42,824,058 |
| Device frames produced | 42,824,053 |
| Host − device frames | −3,687 |
| Startup frames (first sample no. 120) | ~120 |
| Estimated transport loss | ~3,567 |
| Visible sequence gaps | 1,003 / 797 events |
| **Visible gap fraction** | **0.00234 %** |
| **Reconciled gap fraction** | **0.00833 %** |
| Max visible gap | 205 samples (~0.83 s) |
| Max host timestamp gap | 19.188 s |
| `fs_effective` (host) | 247.803 SPS |
| `fs_effective` (meta) | 247.801 SPS |

The 8-bit OpenBCI sample number sees 1,003 missing samples: 794 single-sample
gaps, 2 two-sample gaps, and one 205-sample gap. Duplicates: 0; max step: 206.
The device-frame reconciliation gives the more conservative estimate:
42,824,053 − 120 − 42,820,366 = **~3,567 lost frames (0.00833 %)**.
The 2,564-frame difference between the two estimates is consistent with
8-bit aliasing of gaps longer than 255 samples (2,564 = 10 × 256 + 4),
concentrated in the single late-run burst described below.

## Device counters

Start status (`meta.json`): all counters zero (opening COM6 resets the ESP32;
the recorder waits 1.5 s and reconfigures). End status, captured before the
port was closed:

| Counter | Start | End | Δ |
|---|---:|---:|---:|
| drdy | 0 | 42,824,058 | +42,824,058 |
| frames produced | 0 | 42,824,053 | +42,824,053 |
| sync_error | 0 | 2 | +2 |
| spi_error | 0 | 0 | 0 |
| timeout | 0 | 93,899 | +93,899 |
| queue_overrun | 0 | 0 | 0 |
| transport_drop | 0 | 0 | **0** |
| verify_error | 0 | 0 | 0 |

`transport_drop = 0`, `queue_overrun = 0`, `spi_error = 0`: the board and the
ESP32 UART output preserved the stream. The `timeout` counter is the firmware's
DRDY-wait timeout (`drdyTimeout`): 93,899 / 172,801 s = **0.543 s⁻¹**, the same
rate as the 2 h Windows run (3,934 / 7,201 s = 0.546 s⁻¹). Three consecutive
timeouts would stop acquisition; the run stayed in `READY` and never hit that
condition. `timeout` and `sync_error` are latency/synchronisation counters,
not data-loss counters. `sync_error = 2` is negligible.

## Gap rate per 4 h

| Time (h) | Received | Visible missing | Gap events | Gap rate |
|---|---:|---:|---:|---:|
| 0–4 | 3,567,801 | 71 | 71 | 0.00199 % |
| 4–8 | 3,570,881 | 60 | 60 | 0.00168 % |
| 8–12 | 3,569,402 | 59 | 59 | 0.00165 % |
| 12–16 | 3,566,697 | 66 | 66 | 0.00185 % |
| 16–20 | 3,567,768 | 70 | 70 | 0.00196 % |
| 20–24 | 3,566,662 | 69 | 69 | 0.00193 % |
| 24–28 | 3,565,732 | 70 | 70 | 0.00196 % |
| 28–32 | 3,569,994 | 72 | 71 | 0.00202 % |
| 32–36 | 3,569,628 | 51 | 51 | 0.00143 % |
| 36–40 | 3,568,629 | 64 | 64 | 0.00179 % |
| 40–44 | 3,569,740 | 74 | 74 | 0.00207 % |
| 44–48 | 3,567,432 | 277 | 72 | 0.00776 % |

The first 44 h are flat at 0.0014–0.0021 %; there is no upward drift. The last
bin contains the single late-run burst.

## The 14:25 UTC event

The largest host timestamp gap is 19.188 s:
`2026-11-26T14:24:49.365Z → 2026-11-26T14:25:08.552Z`
(22:24:49 → 22:25:08 CST). Across that gap the sample number advances
124 → 125, so the wall-clock jump itself did not lose a sample. At
14:25:08.592Z the sequence jumps 65 → 15: 205 visible missing samples.
The device-frame reconciliation implies a true burst of about
205 + 10 × 256 = **2,765 samples (~11.16 s)**, with ~2,560 hidden by the
8-bit wrap; the remainder of the reconciled loss is spread over the
single/double gaps.

No Kernel-Power events (including 506/507/566) were logged in
22:15–22:35 CST, and no System warning/error was logged in 22:24–22:26:30.
The event is therefore host-side (I/O or scheduling stall), not an S0 sleep
and not a device-side drop: the device counters show no transport drop or
queue overrun. Excluding this burst, the reconciled loss is ~0.0019 %.

## RSS and watchdog

| Item | Value |
|---|---:|
| RSS samples | 2,880 |
| RSS min / mean / max | 12.8 / 13.9 / 22.4 MB |
| RSS first / last | 22.1 / 13.0 MB |
| Watchdog samples | 2,846 |
| Watchdog `ok` | 2,845 |
| Watchdog `recorder-exited` | 1 |
| Max stalled seconds | 0 |

The streaming recorder keeps memory constant; the 2 h pre-streaming run used
535 MB. The 48 h run never exceeded 22.4 MB and ended at 13.0 MB.
No `STALL_ALERT.txt` was produced. The watchdog's 5 min no-growth threshold
did not fire for the 11 s burst.

## Signal floor (raw, shorted input)

Counts are raw ADS1299 24-bit values at gain 24; LSB = 4.5/(24·2²³) =
2.235 × 10⁻⁸ V = 0.02235 µV.

| Channel | Mean (counts) | Std (counts) | Std (µV) |
|---|---:|---:|---:|
| ch1 | −937.8 | 6.14 | 0.137 |
| ch2 | −1427.5 | 6.27 | 0.140 |
| ch3 | −789.7 | 6.19 | 0.138 |
| ch4 | −1490.8 | 6.24 | 0.139 |
| ch5 | −1028.9 | 6.08 | 0.136 |
| ch6 | −1317.4 | 6.26 | 0.140 |
| ch7 | −1448.1 | 6.32 | 0.141 |
| ch8 | −871.3 | 6.17 | 0.138 |

This is the raw 48 h standard deviation, not a band-limited or detrended
noise floor; the 2 h analysis reported a 0.01–5 Hz band floor of
0.04–0.46 µV. The raw values are consistent with a shorted input and show no
channel-specific anomaly.

## A/B comparison

| Path | Duration | Gap fraction | Missing | Max gap |
|---|---:|---:|---:|---:|
| usbipd + WSL | 7,200 s | 2.107 % overall / 1.566 % steady | 37,557 | 182 |
| Windows native COM6 | 7,200 s | 0.00258 % visible | 46 | 1 |
| **Windows native COM6** | **172,801 s** | **0.00234 % visible / 0.00833 % reconciled** | **1,003 visible / ~3,567 reconciled** | **205 visible (~2,765 reconciled burst)** |

The 48 h Windows run is ~253× cleaner than the usbipd soak on the reconciled
metric (~900× on the visible metric), and ~240× below the 2 % T6 threshold.
The one late-run host stall is the only significant deviation.

## Verdict

- **PASS** on the T6 < 2 % criterion: 0.00833 % reconciled, ~240× margin.
- The device and firmware preserved the stream: `transport_drop = 0`,
  `queue_overrun = 0`, `spi_error = 0`, `verify_error = 0`.
- No S0 sleep, no watchdog stall, no memory growth.
- The remaining loss is host-side: one ~11 s burst at ~47 h, plus
  single-sample gaps at a flat ~0.0019 % rate.
- Windows native COM is 48 h-grade for the short-mode bench load.

## Caveats

1. Shorted input, `mode short`; no electrodes, agar, or biological signal.
2. The host was in normal interactive use; the late burst may reflect host
   I/O or scheduling, not the board.
3. OpenBCI frames carry no DRDY timestamp; the time base is the 8-bit sample
   number plus the host wall clock. Gaps longer than 255 samples alias in the
   sample number; the device-frame reconciliation is the conservative metric.
4. The 19.188 s timestamp gap and the 205-step alias occur together; the exact
   split between buffered frames, host clock movement, and true loss cannot be
   resolved from the 8-bit counter alone.
5. Raw data (`raw.bin`, `samples.csv`, raw `meta.json`) remain on `C:` and are
   not copied into this evidence directory. The recorder manifest was verified
   with `sha256sum -c` (`raw.bin: OK`, `samples.csv: OK`, `meta.json: OK`).
6. The `meta.json` in this directory is sanitized (`host` → `workstation`);
   its hash therefore differs from the recorder manifest. The raw measurement
   bytes are unchanged.

## Next

1. T3–T5 (electrode/agar drift) when materials are available; then the 3-dish
   pilot.
2. Sequence-gap watchdog (implemented 2026-11-27 in
   `run_scripts/watchdog.py`): alerts on a sample-number step > 2 or on a
   host timestamp gap > 1 s, instead of only on 5 min of no file growth.
3. For runs that need unambiguous gap accounting, use BCIKit native WiFi
   frames (32-bit sequence/timestamps) or periodically reconcile the device
   `frames` counter; the 8-bit OpenBCI sample number cannot distinguish
   205 from 2,765 missing samples.
