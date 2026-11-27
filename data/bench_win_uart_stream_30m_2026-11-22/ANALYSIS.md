# Windows COM UART — 30 min streaming validation on a local C: disk (2026-11-22)

Run: 2026-11-22 23:26:07–23:56:17 CST (UTC 15:26:07), 1800 s requested,
1801.16 s host duration, `mode short`, 250 SPS nominal, 1 board, gain 24,
**Windows native COM6** (`D:\phy\python.exe` 3.14.2, pyserial 3.5), recorder
`host/bcikit_openbci.py` with the 2026-11-22 streaming refactor
(`raw.bin` written incrementally, Welford channel statistics,
`--progress-every 60`, end-of-run status captured before close). The output
was written to a **local C: directory** (not the WSL 9p share) to validate the
48 h output path. The host was in normal interactive use.

Command (Windows Python, paths abbreviated):

    python.exe <repo>\host\bcikit_openbci.py --port COM6 --mode short \
        --duration 1800 --outdir C:\...\win_uart_stream_30m_2026-11-22 \
        --label win-uart-stream-30m --note streaming-recorder-c-drive-test \
        --progress-every 60

## Result (measured)

| Item | Value |
|---|---:|
| Frames received | 445,901 |
| Host duration | 1801.16 s |
| Sample-number span | 445,907 |
| Gap events | 7 |
| Missing samples | 7 |
| **Gap fraction** | **0.00157 %** |
| Max step | 2 (single-sample) |
| Zero/duplicate steps | 0 |
| `fs_effective` (sample clock) | 247.726 SPS |
| `fs_effective` (host clock) | 247.723 SPS |
| Sample–host clock difference | 0.0033 SPS = 0.0013 % (≈ gap fraction) |

All 7 gaps are one sample (`{1: 7}`). The first captured sample number was
123. The device produced 446,033 frames; the host received 445,901; the
difference is 132 = 123 startup frames + 7 transport gaps + 2 trailing
frames produced after the last captured sample.

## Device counters

Start status: all counters zero (opening COM6 resets the ESP32; the recorder
waits 1.5 s and reconfigures). End status, captured before the port closed:

| Counter | Start | End | Δ |
|---|---:|---:|---:|
| drdy | 0 | 446,037 | +446,037 |
| frames produced | 0 | 446,033 | +446,033 |
| sync_error | 0 | 1 | +1 |
| spi_error | 0 | 0 | 0 |
| timeout | 0 | 1,028 | +1,028 |
| queue_overrun | 0 | 0 | 0 |
| transport_drop | 0 | 0 | **0** |
| verify_error | 0 | 0 | 0 |

`transport_drop = 0`, `queue_overrun = 0`, `spi_error = 0`: the board and the
ESP32 UART output preserved the stream. The `timeout`/`sync_error` counters
are the same order as the 2 h run and did not cause drops.

## Memory (streaming refactor)

`memory.csv` samples the recorder RSS every 60 s (31 samples over the run):

| Item | Value |
|---|---:|
| Min RSS | 21.1 MB |
| Max RSS | 21.6 MB |
| First / last | 21.1 / 21.2 MB |
| Growth over 30 min | ≤0.5 MB, no trend |

The old recorder reached 535 MB at 2 h. The streaming version is flat at
~21 MB, as intended. The memory log is part of this evidence bundle.

## Signal floor (short mode, 0.01–5 Hz)

ch1 0.040, ch2 0.040, ch3 0.040, ch4 0.038, ch5 0.039, ch6 0.038,
ch7 0.039, ch8 0.039 µV RMS. Binned drift ≤7.1e-5 mV/h. The board is at its
quiet floor; no host-use transients were captured in this run.

## Verdict

- **PASS**: 7 single-sample gaps in 445,907 samples (0.00157 %) over 30 min,
  with `transport_drop = 0`.
- The streaming refactor is validated end to end: constant memory, incremental
  `raw.bin`, online statistics matching an independent CSV recomputation
  (mean 3e-11, std 1e-12, min/max exact), and end-of-run status capture.
- The **local C: output path works**; this removes the WSL 9p dependency for
  the 48 h run. D: has only 8.4 GB free, so C: is the safe target.

## Caveats

1. 30 min is a validation run, not the 48 h soak. The transport was already
   validated over 2 h (0.00258 %); this run validates the streaming recorder
   and the C: path.
2. The host was in normal interactive use, not a CPU/disk saturation test.
3. `stdout.log` was sanitized (`wrote C:\...` → `wrote <outdir>`), `meta.json`
   host was replaced with `workstation`, and `bench_summary.json` `csv` path
   was relativized to `samples.csv`. Raw measurement bytes (`raw.bin`,
   `samples.csv`) are unchanged. The manifest was regenerated after adding
   this file, `timeline.png`, `memory.csv`, and the logs.
4. The first/last sample accounting includes 123 startup-discarded frames and
   2 trailing frames; these are not transport losses.

## Next

1. Schedule the 48 h Windows COM soak on the local C: disk, with the same
   streaming recorder and `--progress-every 60`; monitor `memory.csv`.
2. After 48 h, analyze gaps/end counters, copy the finalized summary (not the
   raw data) back to the WSL evidence tree, and decide data retention.
3. Then T3–T5 (electrodes/agar) and the 3-dish pilot.
