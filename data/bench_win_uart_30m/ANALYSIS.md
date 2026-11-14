# Windows COM UART — 30 min A/B against the usbipd soak (2026-11-12)

Run: 2026-11-12 23:09:55–23:39:55 CST, 1800 s, `mode short`, 250 SPS,
1 board, gain 24, **Windows native COM6** (`D:\phy\python.exe`, pyserial 3.5),
host in active use by the user during the run.

Command (Windows Python, script on the WSL share):

    python.exe \\wsl.localhost\Ubuntu\path\to\physarum-lab\host\bcikit_openbci.py \
        --port COM6 --mode short --duration 1800 \
        --outdir D:\physarum-data\win_uart_T6_30m_loaded \
        --label win-uart-30m-loaded --note "host in active use by user during run"

## Result (measured)

| Item | Value |
|---|---:|
| Frames received | 445,637 |
| Host duration | 1800.0 s |
| Host rate | 247.58 SPS |
| Gap events | 14 |
| Missing samples | 14 |
| **Gap fraction** | **0.0031 %** |
| Max step | 2 (single-sample) |
| Zero/duplicate steps | 0 |

Gap rate per 5 min: 0.0027 / 0.0054 / 0.0013 / 0.0040 / 0.0013 / 0.0040 %.
No burst; every event is a single missing sample.

Short-mode broadband std (counts): ch1 6.14, ch2 44.88, ch3 27.90,
ch4 6.25, ch5 6.13, ch6 6.16, ch7 6.15, ch8 6.16. Six channels sit at the
0.14 µV floor; ch2/ch3 picked up transients while the host was in use. Not a
transport metric, but the same event did not produce data loss.

## A/B comparison

| Path | Duration | Gap fraction |
|---|---:|---:|
| usbipd + WSL, 2 h soak | 7200 s | **2.107 %** overall / **1.566 %** steady (40–120 min) |
| **Windows native COM6** | 1800 s | **0.0031 %** |

The Windows path is ~500–680× cleaner, **while the host was in active use**.
Combined with the device counters from the usbipd soak (transport_drop +0,
queue_overrun 0, spi_error 0), the loss is attributable to the usbipd/WSL
serial path, not the ADS1299, the ESP32 UART output, or the firmware.

## Caveats and observations

1. **Opening COM6 resets the ESP32.** `meta.json` start counters are all zero
   (fresh boot), and a new port open after the run produced another reset
   (`device_status_end.txt`: drdy=0, frames=0). The run itself is valid — the
   recorder configured after the reset — but **end-of-run device counters are
   not recoverable this way**. The recorder should read `status` before
   closing the port; for the Windows path it should also sleep 1–2 s after
   open before sending commands. This is a tool gap, not a data gap.
2. Duration is 30 min vs the 2 h soak. The Windows path still needs a longer
   run (2 h+) before committing to 48 h; the 30 min result is strong but not
   a 48 h guarantee.
3. The host was in active use during this run, which makes the clean result
   more conservative: the usbipd soak was mostly idle, and it still lost 1.57 %
   in steady state.
4. `raw.bin` / `samples.csv` / `meta.json` / `SHA256SUMS` were produced by the
   recorder; `ANALYSIS.md`, `timeline.png`, `device_status_end.txt` were added
   after the run and the manifest regenerated.

## Verdict

- **Windows native COM is a viable UART path** for long recordings: 0.0031 %
  over 30 min under load, no burst losses.
- The 48 h UART option is now **online and usbipd-free**, at the cost of no
  DRDY timestamp (OpenBCI frames, 1-byte sample number).
- The BCIKit native WiFi path remains the option when device DRDY timestamps
  are required; its N1 test is still pending.

## Next

1. Add end-of-run `status` capture (and a post-open delay) to
   `bcikit_openbci.py`.
2. Run a 2 h Windows COM soak to match the usbipd soak duration.
3. Decide 48 h transport: Windows COM UART (online) vs native WiFi
   (timestamps, offline/​USB-tethered).
