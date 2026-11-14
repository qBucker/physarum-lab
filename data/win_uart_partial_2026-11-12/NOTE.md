# Windows COM6 UART — exploratory partial (2026-11-12 22:59:46–23:07:50)

Stopped early because the laptop was needed. NOT a formal evidence artifact:
no meta.json, no raw.bin, no SHA256SUMS (the recorder writes them at the end).

| Item | Value |
|---|---:|
| Frames | 119,095 |
| Host duration | 481.1 s |
| Host rate | 247.54 SPS |
| Gaps | 3 events / 3 samples |
| Gap fraction | **0.0025 %** |
| Max step | 2 (single-sample) |

Contrast: usbipd + WSL 2 h soak steady state was **1.57 %** (overall 2.107 %).
This partial suggests the loss is in the usbipd/WSL path, not the board or the
ESP32 UART output. A clean 30 min run (idle host) is still required for the
formal comparison.
