#!/usr/bin/env python3
"""Live rolling oscilloscope for BCIKit M1 over UART (OpenBCI frames).

Switches the board to the requested mode (default: internal test signal),
streams at 250 SPS and plots a rolling window in mV. Closing the window (or
Ctrl+C) stops the stream and sends `s` to the device.

Usage:
    python3 host/live_view.py --port /dev/ttyUSB0 --mode test
    python3 host/live_view.py --port /dev/ttyUSB0 --mode short

Notes:
- UART OpenBCI frames only; 250 SPS only. BLE/Studio must be disconnected
  (an active BLE session can block UART commands).
- This is a viewing tool, not a recorder: nothing is written to disk.
"""

import argparse
import os
import sys
import time
from collections import deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcikit_openbci as bc  # noqa: E402  (configure + parse_frame)

import serial  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation  # noqa: E402

LSB_MV = 22.3517e-6          # 4.5 V / (24 * 2**23) in mV per count
PACKET = 33
START_BYTE = 0xA0
STOP_BYTE = 0xC0


def read_frames(ser, buf, limit=600):
    chunk = ser.read(4096)
    if chunk:
        buf.extend(chunk)
    frames = []
    while len(buf) >= PACKET and len(frames) < limit:
        if buf[0] != START_BYTE:
            idx = buf.find(bytes([START_BYTE]))
            if idx < 0:
                buf.clear()
                break
            del buf[:idx]
            continue
        if buf[PACKET - 1] != STOP_BYTE:
            del buf[0]
            continue
        frames.append(bytes(buf[:PACKET]))
        del buf[:PACKET]
    return frames


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--mode", default="test",
                    choices=["eeg", "diff", "test", "short"])
    ap.add_argument("--channel", type=int, default=1, help="1-based focus channel")
    ap.add_argument("--window", type=float, default=4.0, help="rolling window (s)")
    args = ap.parse_args()

    ser = serial.Serial(args.port, 115200, timeout=0.01)
    try:
        try:
            print("configuring mode", args.mode, flush=True)
            bc.configure(ser, args.mode, 250, "0xFF")
        except Exception as exc:  # show the failure in a window, not just stdout
            import tkinter.messagebox as mb
            mb.showerror(
                "BCIkit live view",
                f"Device configuration failed:\n{exc}\n\n"
                "Check that BCIKit Studio / BLE is disconnected, then retry.")
            return 1

        ser.reset_input_buffer()
        ser.write(b"start\n")
        time.sleep(0.5)
        ser.reset_input_buffer()
        t0 = time.time()
        print("streaming; close the window to stop", flush=True)

        n_max = int(args.window * 260) + 100
        tbuf = deque(maxlen=n_max)
        buf = [deque(maxlen=n_max) for _ in range(8)]
        rbuf = bytearray()
        n_total = 0

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 7), sharex=True,
            gridspec_kw={"height_ratios": [2, 1]})
        fig.canvas.manager.set_window_title("BCIkit M1 live view")
        ax1.set_ylabel("ch%d (mV)" % args.channel)
        ax2.set_ylabel("all channels (mV)")
        ax2.set_xlabel("time (s, rolling)")
        for ax in (ax1, ax2):
            ax.grid(alpha=0.3)
        line1, = ax1.plot([], [], lw=1.2, color="#1f4e79")
        colors = plt.cm.tab10(np.linspace(0, 1, 8))
        lines2 = [ax2.plot([], [], lw=0.7, alpha=0.7,
                           color=colors[j])[0] for j in range(8)]
        status = fig.text(0.01, 0.005, "", fontsize=9, color="#444")
        fig.tight_layout(rect=(0, 0.02, 1, 1))

        def update(_frame):
            nonlocal n_total
            frames = read_frames(ser, rbuf)
            now = time.time()
            for f in frames:
                _, vals = bc.parse_frame(f)
                tbuf.append(now)
                for j in range(8):
                    buf[j].append(vals[j])
                n_total += 1
            if not tbuf:
                return
            n = len(tbuf)
            t = (np.arange(n) - (n - 1)) / 250.0
            y = np.array([np.fromiter(buf[j], float, n) for j in range(8)]) * LSB_MV
            line1.set_data(t, y[args.channel - 1])
            for j in range(8):
                lines2[j].set_data(t, y[j])
            for ax in (ax1, ax2):
                lo, hi = float(np.min(y)), float(np.max(y))
                pad = max(0.2, 0.15 * (hi - lo))
                y0, y1 = ax.get_ylim()
                if lo - pad < y0 or hi + pad > y1:
                    ax.set_ylim(lo - pad, hi + pad)
            ax1.set_xlim(-args.window, 0)
            elapsed = now - t0
            fps = n_total / elapsed if elapsed > 0 else 0.0
            status.set_text(
                "mode=%s  frames=%d  avg=%.1f fps  window=%.1fs  "
                "gain=24  LSB=22.35 nV/count" % (args.mode, n_total, fps, args.window))

        anim = FuncAnimation(fig, update, interval=150, blit=False,
                             cache_frame_data=False)
        try:
            plt.show()
        finally:
            anim.event_source.stop()
        return 0
    finally:
        try:
            ser.write(b"s")
            time.sleep(0.2)
        except Exception:
            pass
        ser.close()


if __name__ == "__main__":
    sys.exit(main())
