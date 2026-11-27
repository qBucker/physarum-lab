# Windows COM UART — 2 h soak (2026-11-22)

Run: 2026-11-22 20:56:01–22:56:02 CST (UTC 12:56:01), 7200 s requested,
7201.15 s host duration, `mode short`, 250 SPS nominal, 1 board, gain 24,
**Windows native COM6** (`D:\phy\python.exe` 3.14.2, pyserial 3.5), recorder
`host/bcikit_openbci.py` with the 2026-11-16 diff (1.5 s post-open delay,
`device_status_start/end`). The script was read from the WSL share and the
output was written back over the same share; the host was in normal
interactive use during the run.

Command (Windows Python, paths abbreviated):

    python.exe <repo>\host\bcikit_openbci.py --port COM6 --mode short \
        --duration 7200 --outdir data\bench_win_uart_2h_2026-11-22 \
        --label win-uart-2h --note win-uart-2h-post-11-16-recorder

## Result (measured)

| Item | Value |
|---|---:|
| Frames received | 1,784,268 |
| Host duration | 7201.15 s |
| Sample-number span | 1,784,313 |
| Gap events | 46 |
| Missing samples | 46 |
| **Gap fraction** | **0.00258 %** |
| Max step | 2 (single-sample) |
| Zero/duplicate steps | 0 |
| `fs_effective` (sample clock) | 247.821 SPS |
| `fs_effective` (host clock) | 247.815 SPS |
| Sample–host clock difference | 0.006 SPS = **0.0024 %** (≈ gap fraction) |

The first captured sample number was 125, so ~125 frames produced during the
0.5 s start flush were not captured. The device produced 1,784,438 frames;
the host received 1,784,268; the difference is 170 = ~125 startup frames +
45–46 single-sample transport gaps. All 46 gaps are one sample; there are no
bursts.

## Device counters

Start status (`meta.json`): all counters zero (opening COM6 resets the ESP32;
the recorder waits 1.5 s and reconfigures). End status, captured before the
port was closed:

| Counter | Start | End | Δ |
|---|---:|---:|---:|
| drdy | 0 | 1,784,444 | +1,784,444 |
| frames produced | 0 | 1,784,438 | +1,784,438 |
| sync_error | 0 | 3 | +3 |
| spi_error | 0 | 0 | 0 |
| timeout | 0 | 3,934 | +3,934 |
| queue_overrun | 0 | 0 | 0 |
| transport_drop | 0 | 0 | **0** |
| verify_error | 0 | 0 | 0 |

`transport_drop = 0`, `queue_overrun = 0`, `spi_error = 0`: the board and the
ESP32 UART output preserved the stream. The `timeout` and `sync_error`
counters are nonzero but are the same order as the usbipd soak (+4,396 / +4)
and did not cause transport drops or queue overruns; they are not data-loss
counters.

## Gap rate per 10 min

```
 0–10  0.00403%   40–50  0.00067%   80–90   0.00134%
10–20  0.00202%   50–60  0.00202%   90–100  0.00269%
20–30  0.00336%   60–70  0.00404%  100–110  0.00067%
30–40  0.00538%   70–80  0.00337%  110–120  0.00135%
```

No upward trend; the worst 10 min bin is 0.0054 %, the best 0.0007 %. The
usbipd soak, by contrast, started at 3.19 % and settled at 1.3–1.8 %.

## Signal floor (short mode, 0.01–5 Hz)

ch1 0.360, ch2 0.435, ch3 0.459, ch4 0.118, ch5 0.048, ch6 0.043,
ch7 0.041, ch8 0.040 µV RMS. Binned drift ≤ 2.5e-5 mV/h. ch1–ch3 are
elevated (0.36–0.46 µV) relative to the quiet channels (0.04–0.12 µV),
consistent with occasional transients during interactive use; the analog
floor is unchanged.

## A/B comparison

| Path | Duration | Gap fraction | Missing samples | Max gap |
|---|---:|---:|---:|---:|
| usbipd + WSL | 7200 s | **2.107 %** overall / **1.566 %** steady | 37,557 | 182 |
| Windows native COM6 | 1800 s | **0.0031 %** | 14 | 1 |
| **Windows native COM6** | **7200 s** | **0.00258 %** | **46** | **1** |

The 2 h Windows path is ~817× cleaner than the usbipd soak overall (~607×
against its steady state), with every loss a single sample and no trend.
Combined with the device counters (transport_drop = 0 in both paths), the
loss is attributable to the usbipd/WSL serial path, not the ADS1299, the
ESP32 UART output, or the firmware.

## Verdict

- **PASS** on the T6 < 2 % criterion, by ~775× (0.00258 %).
- **Windows native COM is 48 h-grade on transport** for the short-mode
  bench load, under normal host use, with the 11-16 recorder.
- The 2026-11-16 recorder diff is validated end to end: the 1.5 s post-open
  delay survives the DTR/RTS reset and the end-of-run `status` is captured
  before the port closes (no more post-reset counters).

## Caveats

1. The host was in normal interactive use, not a CPU/disk saturation test.
2. The output was written over the WSL 9p share. This did not cause drops,
   but a 48 h run should write to a local Windows disk to remove the WSL
   dependency and the 9p overhead.
3. OpenBCI frames carry no DRDY timestamp; the time base is the 8-bit sample
   number, reconstructed across wraps. Absolute frequency is per run
   (`fs_effective`).
4. **Recorder memory scales with run length.** RSS was 535 MB at 2 h
   (`raw_chunks` + the `samples` list). A 48 h run would need ~13 GB and
   risks OOM. Before 48 h, stream `raw.bin` to disk and compute channel
   statistics online (Welford) instead of retaining every sample.
5. At 2 h the CSV is 174 MB and `raw.bin` is 59 MB; a 48 h run extrapolates
   to ~4.2 GB + ~1.4 GB, which fits the current disk.
6. Metadata sanitization: the `meta.json` host field was replaced with
   `workstation` (local hostname removed); `bench_summary.json` `csv` path
   → `samples.csv`. Raw measurement bytes
   (`raw.bin`, `samples.csv`) are unchanged. The manifest was regenerated
   after adding this file and `timeline.png`.

## Next

1. Recorder: streaming `raw.bin`, online channel stats, constant memory;
   keep the 1.5 s delay and end-status capture.
2. 48 h path decision: Windows COM UART is now the default (online, no DRDY
   timestamp); BCIKit native WiFi frames remain the option when device
   timestamps are required (N1 pending).
3. Run the 48 h soak on a local Windows disk, then T3–T5 (electrodes/agar)
   and the 3-dish pilot.
