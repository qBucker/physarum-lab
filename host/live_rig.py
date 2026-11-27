#!/usr/bin/env python3
"""BCIKit M1 live rig monitor: 3D plate + rolling traces + recording.

Upgrades host/live_view.py into an operator console for bench and plate runs:

  * 3D Petri dish with the 8 electrode sites coloured by the band-limited RMS;
  * rolling 8-channel traces (raw, uV) and live status (effective SPS, gaps,
    saturation, RMS, elapsed, file);
  * records the same evidence bundle as the bench recorders: raw.bin (UART),
    samples.csv, meta.json, SHA256SUMS;
  * two sources behind one interface: BCIKit UART (OpenBCI 33-byte frames,
    250 SPS) and a synthetic T2-like stream for demos and CI.  The WiFi native
    source (host/bcikit_native.py) plugs into the same interface.

Usage:
    python3 host/live_rig.py --synthetic
    python3 host/live_rig.py --port /dev/ttyUSB0 --mode test --outdir data/live_t2
    python3 host/live_rig.py --synthetic --screenshot docs/live-rig.png

Notes:
- UART is OpenBCI frames only: 250 SPS, 8 channels, gain 24.  BLE/Studio must
  be disconnected (an active BLE session blocks UART commands).
- The UART sample counter is 8-bit; gaps estimate drops but do not prove them.
- This viewer is not a substitute for the 2 h soak recorders; use it to watch
  a run, then keep the recorded bundle as evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pyvista as pv

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import bcikit_openbci as bc
except Exception:  # pragma: no cover - allow synthetic-only use
    bc = None

RATE = 250
GAIN = 24
LSB_V = 4.5 / (GAIN * 2 ** 23)          # 22.35 nV/count
LSB_UV = LSB_V * 1e6
FULL_SCALE_MV = 187.5
N_CH = 8
DISH_RADIUS_MM = 45.0
ELECTRODE_RADIUS_MM = 30.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------

class SyntheticSource:
    """T2-like stream: 8 channels, 0.9766 Hz / 3.742 mVpp + 1/f noise."""

    name = "synthetic"

    def __init__(self, outdir=None, label="synthetic", note=""):
        self.outdir = outdir
        self.label = label
        self.note = note
        self.rng = np.random.default_rng(20261114)
        self.n = 0
        self.t0 = None
        self.csv = None
        self.csv_path = None
        self.raw = None
        self.raw_path = None
        self.meta_path = None
        self.sample_counter = 0
        self.drops = 0
        self.sat = 0
        self.started_at = None
        self._noise = None

    def _build_noise(self):
        n = RATE * 60
        f = np.fft.rfftfreq(n, 1.0 / RATE)
        white = self.rng.normal(size=(n, N_CH))
        spec = np.fft.rfft(white, axis=0)
        spec[1:] /= np.sqrt(np.maximum(f[1:], 1e-6))[:, None]
        noise = np.fft.irfft(spec, n=n, axis=0)
        noise -= noise.mean(axis=0)
        noise /= noise.std(axis=0)
        self._noise = (noise * 10.0).astype(np.float32)   # 10 uV RMS

    def start(self):
        self.t0 = time.time()
        self.started_at = utc_now()
        self.n = 0
        self.sample_counter = 0
        self.drops = 0
        self.sat = 0
        self._build_noise()
        if self.outdir:
            os.makedirs(self.outdir, exist_ok=True)
            self.csv_path = os.path.join(self.outdir, "samples.csv")
            self.csv = open(self.csv_path, "w", newline="")
            self.csv.write("host_time_iso,host_unix,sample_number," +
                           ",".join(f"ch{i + 1}" for i in range(N_CH)) + "\n")

    def read(self):
        now = time.time()
        target = int((now - self.t0) * RATE)
        n = target - self.n
        if n <= 0:
            return None
        idx = (self.n + np.arange(n)) % self._noise.shape[0]
        t = (self.n + np.arange(n)) / RATE
        uv = self._noise[idx].copy()
        for ch in range(N_CH):
            uv[:, ch] += 1871.0 * np.sin(2 * np.pi * 0.9766 * t + 0.13 * ch)
        counts = np.round(uv / LSB_UV).astype(np.int32)
        saturated = int((np.abs(counts) > 2 ** 23 - 2).sum())
        self.sat += saturated
        self.n = target
        self.sample_counter = (self.sample_counter + n) % 256
        nums = (self.sample_counter - n + np.arange(n)) % 256
        if self.csv is not None:
            for k in range(n):
                self.csv.write(
                    f"{utc_now()},{now - (n - k) / RATE:.6f},{int(nums[k])}," +
                    ",".join(str(int(v)) for v in counts[k]) + "\n")
        return dict(counts=counts, raw=None, drop_delta=0,
                    saturation=saturated, elapsed=now - self.t0)

    def stop(self):
        if self.csv is not None:
            self.csv.close()
            self.csv = None
        if self.outdir:
            self._write_meta()

    def _write_meta(self):
        meta = {
            "label": self.label, "note": self.note, "source": "synthetic",
            "mode": "synthetic", "rate_sps": RATE, "channels": "0xFF",
            "gain": GAIN, "started_at_utc": self.started_at,
            "elapsed_s": (time.time() - self.t0) if self.t0 else None,
            "host": platform.node(), "platform": platform.platform(),
            "notes": ["Synthetic T2-like stream: 0.9766 Hz, 3.742 mVpp, "
                      "10 uV RMS 1/f; not a recording of a device."],
        }
        self.meta_path = os.path.join(self.outdir, "meta.json")
        with open(self.meta_path, "w") as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
        names = [self.csv_path, self.meta_path]
        with open(os.path.join(self.outdir, "SHA256SUMS"), "w") as fh:
            for path in names:
                if path and os.path.exists(path):
                    fh.write(f"{sha256_file(path)}  {os.path.basename(path)}\n")


class UARTSource:
    """BCIKit UART, OpenBCI 33-byte frames, 250 SPS, 8 channels."""

    name = "uart"

    def __init__(self, port, mode="test", outdir=None, label="", note=""):
        self.port = port
        self.mode = mode
        self.outdir = outdir
        self.label = label
        self.note = note
        self.ser = None
        self.buf = bytearray()
        self.raw_chunks = []
        self.csv = None
        self.csv_path = None
        self.raw_path = None
        self.meta_path = None
        self.setup_log = {}
        self.samples = []
        self.prev_sample = None
        self.drops = 0
        self.sat = 0
        self.started_at = None
        self.t0 = None
        self.raw_path = None

    def start(self):
        if serial is None:
            raise RuntimeError("pyserial is required for UART mode")
        if bc is None:
            raise RuntimeError("bcikit_openbci.py not importable")
        self.ser = serial.Serial(self.port, 115200, timeout=0.01)
        self.setup_log = bc.configure(self.ser, self.mode, RATE, "0xFF")
        self.ser.reset_input_buffer()
        self.ser.write(b"start\n")
        time.sleep(0.5)
        self.ser.read(8192)
        self.started_at = utc_now()
        self.t0 = time.time()
        if self.outdir:
            os.makedirs(self.outdir, exist_ok=True)
            self.csv_path = os.path.join(self.outdir, "samples.csv")
            self.csv = open(self.csv_path, "w", newline="")
            self.csv.write("host_time_iso,host_unix,sample_number," +
                           ",".join(f"ch{i + 1}" for i in range(N_CH)) + "\n")
            self.raw_path = os.path.join(self.outdir, "raw.bin")

    def read(self):
        chunk = self.ser.read(4096)
        if chunk:
            self.raw_chunks.append(chunk)
            self.buf.extend(chunk)
        frames = []
        while len(self.buf) >= 33 and len(frames) < 800:
            if self.buf[0] != 0xA0:
                idx = self.buf.find(b"\xa0")
                if idx < 0:
                    self.buf.clear()
                    break
                del self.buf[:idx]
                continue
            if self.buf[32] != 0xC0:
                del self.buf[0]
                continue
            frames.append(bytes(self.buf[:33]))
            del self.buf[:33]
        if not frames:
            return None
        counts = np.empty((len(frames), N_CH), np.int32)
        nums = np.empty(len(frames), np.int32)
        now = time.time()
        for k, frame in enumerate(frames):
            sample, values = bc.parse_frame(frame)
            nums[k] = sample
            counts[k] = values
            if self.prev_sample is not None:
                gap = (sample - self.prev_sample - 1) % 256
                if 0 < gap < 128:
                    self.drops += gap
            self.prev_sample = sample
            if self.csv is not None:
                self.csv.write(f"{utc_now()},{now:.6f},{sample}," +
                               ",".join(str(v) for v in values) + "\n")
        self.samples.extend(counts.tolist())
        saturated = int((np.abs(counts) > 2 ** 23 - 2).sum())
        self.sat += saturated
        return dict(counts=counts, raw=None, drop_delta=0,
                    saturation=saturated, elapsed=now - self.t0)

    def stop(self):
        try:
            self.ser.write(b"s")
            time.sleep(0.3)
            self.ser.read(4096)
        except Exception:
            pass
        try:
            self.ser.close()
        except Exception:
            pass
        if self.csv is not None:
            self.csv.close()
            self.csv = None
        if self.outdir:
            with open(self.raw_path, "wb") as fh:
                for chunk in self.raw_chunks:
                    fh.write(chunk)
            elapsed = time.time() - self.t0 if self.t0 else 0.0
            stats = {}
            if self.samples:
                arr = np.asarray(self.samples)
                for i in range(N_CH):
                    col = arr[:, i]
                    stats[f"ch{i + 1}"] = {
                        "mean_counts": float(col.mean()),
                        "std_counts": float(col.std()),
                        "min_counts": int(col.min()),
                        "max_counts": int(col.max()),
                    }
            meta = {
                "label": self.label, "note": self.note, "source": "uart",
                "mode": self.mode, "rate_sps": RATE, "channels": "0xFF",
                "port": self.port, "baud": 115200, "gain": GAIN,
                "started_at_utc": self.started_at, "elapsed_s": elapsed,
                "frames": len(self.samples),
                "effective_sps": len(self.samples) / elapsed if elapsed else None,
                "sample_drops": self.drops,
                "saturated_samples": self.sat,
                "host": platform.node(), "platform": platform.platform(),
                "firmware_commands": self.setup_log,
                "channel_stats_counts": stats,
                "notes": [
                    "Counts are raw ADS1299 24-bit values at gain 24.",
                    "LSB at gain 24, VREF 4.5 V: 4.5/(24*2^23) = 2.235e-8 V.",
                    "OpenBCI packets omit the ADS1299 status word and DRDY "
                    "timestamp.",
                ],
            }
            self.meta_path = os.path.join(self.outdir, "meta.json")
            with open(self.meta_path, "w") as fh:
                json.dump(meta, fh, indent=2, ensure_ascii=False)
            names = [p for p in (self.raw_path, self.csv_path, self.meta_path)
                     if p and os.path.exists(p)]
            with open(os.path.join(self.outdir, "SHA256SUMS"), "w") as fh:
                for path in names:
                    fh.write(f"{sha256_file(path)}  {os.path.basename(path)}\n")


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------

def make_worker_class():
    from PyQt5 import QtCore

    class SourceWorker(QtCore.QObject):
        samples = QtCore.pyqtSignal(object)
        status = QtCore.pyqtSignal(str)
        failed = QtCore.pyqtSignal(str)

        def __init__(self, source):
            super().__init__()
            self.source = source
            self._stop = False

        @QtCore.pyqtSlot()
        def run(self):
            try:
                self.source.start()
                self.status.emit(f"{self.source.name} started")
                while not self._stop:
                    out = self.source.read()
                    if out is not None:
                        self.samples.emit(out)
                    else:
                        time.sleep(0.005)
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self.failed.emit(str(exc))
            finally:
                try:
                    self.source.stop()
                except Exception:
                    pass
                self.status.emit(f"{self.source.name} stopped")

        def stop(self):
            self._stop = True

    return SourceWorker


# ---------------------------------------------------------------------------
# Qt app
# ---------------------------------------------------------------------------

def run_app(source, screenshot=None):
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from PyQt5 import QtCore, QtGui, QtWidgets
    from pyvistaqt import QtInteractor
    from scipy import signal

    SourceWorker = make_worker_class()

    sos = signal.butter(4, [0.03, 5.0], btype="bandpass",
                        fs=RATE, output="sos")
    zi = signal.sosfilt_zi(sos)

    class TraceCanvas(FigureCanvasQTAgg):
        def __init__(self):
            self.fig = Figure(figsize=(10.0, 2.6), dpi=100)
            self.ax = self.fig.add_subplot(111)
            self.lines = []
            self.palette = ["#1f4e79", "#c0392b", "#1e8449", "#b7950b",
                            "#6c3483", "#117a65", "#a04000", "#5d6d7e"]
            for ch in range(N_CH):
                self.lines.append(self.ax.plot([], [], lw=0.8, alpha=0.85,
                                               color=self.palette[ch],
                                               label=f"ch{ch + 1}")[0])
            self.ax.set_xlabel("time (s, rolling)", fontsize=8)
            self.ax.set_ylabel("ch1-8 (uV)", fontsize=8)
            self.ax.tick_params(labelsize=7)
            self.ax.grid(alpha=0.25)
            self.ax.legend(fontsize=6, ncol=8, loc="upper right",
                           frameon=False)
            self.fig.tight_layout(pad=0.4)
            super().__init__(self.fig)

        def update_data(self, t, y):
            for ch in range(N_CH):
                self.lines[ch].set_data(t, y[:, ch])
            self.ax.set_xlim(float(t[0]), float(t[-1]))
            lo = float(np.percentile(y, 0.5))
            hi = float(np.percentile(y, 99.5))
            pad = max(1.0, 0.12 * (hi - lo))
            self.ax.set_ylim(lo - pad, hi + pad)
            self.draw_idle()

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("BCIKit M1 · Live rig monitor")
            self.resize(1480, 940)
            self.source = source
            self.worker = None
            self.thread = None
            self.recording = False
            self.running = False
            self.nmax = 30 * RATE
            self.tbuf = np.zeros(self.nmax)
            self.ybuf = np.zeros((self.nmax, N_CH))
            self.nfill = 0
            self.n_total = 0
            self.started = None
            self.filter_state = None
            self.rms_uv = np.zeros(N_CH)
            self.phase = 0.0
            self.screenshot = screenshot

            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QVBoxLayout(central)
            root.setContentsMargins(8, 8, 8, 6)
            root.setSpacing(6)

            top = QtWidgets.QHBoxLayout()
            top.setSpacing(8)
            self.plotter = QtInteractor(central)
            self.plotter.set_background("#f7f7f4")
            top.addWidget(self.plotter, 1)

            panel = QtWidgets.QWidget()
            panel.setFixedWidth(330)
            panel.setObjectName("panel")
            top.addWidget(panel)
            v = QtWidgets.QVBoxLayout(panel)
            v.setContentsMargins(10, 8, 10, 8)
            v.setSpacing(8)

            title = QtWidgets.QLabel("Live rig · BCIKit M1")
            title.setObjectName("title")
            v.addWidget(title)
            self.lbl_source = QtWidgets.QLabel("source: —")
            self.lbl_source.setObjectName("sub")
            v.addWidget(self.lbl_source)

            row = QtWidgets.QHBoxLayout()
            self.btn_run = QtWidgets.QPushButton("Start")
            self.btn_run.clicked.connect(self.toggle_run)
            self.btn_shot = QtWidgets.QPushButton("Screenshot")
            self.btn_shot.clicked.connect(self.take_shot)
            row.addWidget(self.btn_run)
            row.addWidget(self.btn_shot)
            v.addLayout(row)

            self.lbl_metrics = QtWidgets.QLabel("—")
            self.lbl_metrics.setObjectName("metrics")
            self.lbl_metrics.setMinimumHeight(150)
            v.addWidget(self.lbl_metrics)
            v.addStretch(1)

            self.lbl_status = QtWidgets.QLabel("idle")
            self.lbl_status.setObjectName("status")
            self.lbl_status.setWordWrap(True)
            v.addWidget(self.lbl_status)

            note = QtWidgets.QLabel(
                "PyVista 3D plate + rolling traces; UART OpenBCI 250 SPS, "
                "gain 24. Recorded bundle: raw.bin / samples.csv / meta.json / "
                "SHA256SUMS. Synthetic mode is a T2-like demo, not a device "
                "recording.")
            note.setObjectName("note")
            note.setWordWrap(True)
            v.addWidget(note)

            root.addLayout(top, 1)
            self.traces = TraceCanvas()
            root.addWidget(self.traces)

            self.setStyleSheet("""
                QWidget { background: #fcfcfa; color: #222; }
                QLabel#title { font-size: 18px; font-weight: 700; }
                QLabel#sub, QLabel#status { color: #6a6a66; font-size: 11px; }
                QLabel#metrics { font-family: "DejaVu Sans Mono", monospace;
                                 background: #f2f6fb; border-radius: 6px;
                                 padding: 8px; color: #163f73; font-size: 10px; }
                QLabel#note { color: #8a8880; font-size: 10px; }
                QPushButton { background: #f2f1ec; border: 1px solid #d9d8d2;
                              border-radius: 5px; padding: 6px 10px; }
                QPushButton:hover { background: #e8eef8; border-color: #2a78d6; }
            """)

            self._build_plate(pv)
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(100)
            self.timer.timeout.connect(self.refresh)
            self.timer.start()

            self.thread = QtCore.QThread(self)
            self.worker = SourceWorker(self.source)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.samples.connect(self.on_samples)
            self.worker.status.connect(self.on_status)
            self.worker.failed.connect(self.on_failed)
            self.thread.start()
            self.running = True
            self.started = time.time()
            self.btn_run.setText("Stop")

            if screenshot:
                QtCore.QTimer.singleShot(3500, self._capture_and_quit)

        def _build_plate(self, pv):
            angles = np.deg2rad(np.arange(N_CH) * 360.0 / N_CH)
            self.positions = np.c_[ELECTRODE_RADIUS_MM * np.cos(angles),
                                   ELECTRODE_RADIUS_MM * np.sin(angles),
                                   np.zeros(N_CH)]
            dish = pv.Cylinder(center=(0, 0, -1), direction=(0, 0, 1),
                               radius=DISH_RADIUS_MM, height=2.0,
                               resolution=96)
            self.plotter.add_mesh(dish, color="#dbe4ee", opacity=0.35,
                                  name="dish")
            self.egrid = pv.PolyData(self.positions)
            self.egrid["rms"] = np.zeros(N_CH)
            self.glyph = self.egrid.glyph(
                geom=pv.Sphere(radius=3.2, theta_resolution=16,
                               phi_resolution=16), scale=False, orient=False)
            self.electrode_actor = self.plotter.add_mesh(
                self.glyph, scalars="rms", cmap="plasma", clim=(0, 2000),
                show_scalar_bar=True, name="electrodes",
                scalar_bar_args={"title": "band RMS (uV)", "n_labels": 5,
                                 "position_x": 0.62, "position_y": 0.06,
                                 "width": 0.30, "height": 0.06})
            labels = [f"E{i + 1}" for i in range(N_CH)]
            self.plotter.add_point_labels(
                self.positions, labels, font_size=11, text_color="#203040",
                shape_color="white", shape_opacity=0.8,
                always_visible=True)
            self.plotter.view_isometric()
            self.plotter.reset_camera()
            self.plotter.camera.zoom(1.15)
            self.plotter.render()

        def on_status(self, text):
            self.lbl_status.setText(text)

        def on_failed(self, text):
            self.running = False
            self.btn_run.setText("Start")
            self.lbl_status.setText(f"failed: {text}")

        def toggle_run(self):
            if not self.running:
                self.running = True
                self.started = time.time()
                self.btn_run.setText("Stop")
                self.lbl_source.setText(f"source: {self.source.name}")
            else:
                self.running = False
                self.worker.stop()
                self.btn_run.setText("Start")
                self.btn_run.setEnabled(False)
                self.lbl_status.setText("stopped; reopen to start a new run")

        def take_shot(self):
            path = os.path.join(os.getcwd(), "live_rig.png")
            self.grab().save(path)
            self.lbl_status.setText(f"screenshot: {path}")

        def _capture_and_quit(self):
            if self.screenshot:
                self.grab().save(self.screenshot)
                print(f"[screenshot] {self.screenshot}")
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(2000)
            QtWidgets.QApplication.quit()

        def on_samples(self, out):
            counts = out["counts"]
            n = counts.shape[0]
            y = counts.astype(np.float64) * LSB_UV
            if self.nfill + n > self.nmax:
                shift = self.nfill + n - self.nmax
                self.ybuf[:-shift] = self.ybuf[shift:]
                self.tbuf[:-shift] = self.tbuf[shift:]
                self.nfill -= shift
            self.tbuf[self.nfill:self.nfill + n] = (
                np.arange(self.nfill, self.nfill + n) / RATE)
            self.ybuf[self.nfill:self.nfill + n] = y
            self.nfill += n
            self.n_total += n
            if self.filter_state is None:
                self.filter_state = zi[:, :, None] * y[0][None, None, :]
            filt, self.filter_state = signal.sosfilt(
                sos, y, axis=0, zi=self.filter_state)
            tail = filt[-min(RATE, len(filt)):]
            self.rms_uv = np.sqrt((tail ** 2).mean(axis=0))

        def refresh(self):
            if self.nfill == 0:
                return
            n = self.nfill
            t = self.tbuf[:n] - self.tbuf[n - 1]
            self.traces.update_data(t, self.ybuf[:n])
            self.egrid["rms"] = self.rms_uv
            self.glyph = self.egrid.glyph(
                geom=pv.Sphere(radius=3.2, theta_resolution=16,
                               phi_resolution=16), scale=False, orient=False)
            self.plotter.remove_actor("electrodes", render=False)
            self.electrode_actor = self.plotter.add_mesh(
                self.glyph, scalars="rms", cmap="plasma",
                clim=(0, 2000),
                show_scalar_bar=False, name="electrodes")
            self.plotter.update_scalar_bar_range((0, 2000))
            self.plotter.render()
            elapsed = time.time() - self.started if self.started else 0.0
            sps = self.n_total / elapsed if elapsed > 0 else 0.0
            rms1 = "  ".join(f"ch{i + 1} {self.rms_uv[i]:6.0f}" for i in range(4))
            rms2 = "  ".join(f"ch{i + 5} {self.rms_uv[i + 4]:6.0f}" for i in range(4))
            self.lbl_metrics.setText(
                f"elapsed {elapsed:7.1f} s   effective {sps:6.1f} SPS\n"
                f"samples {self.n_total:8d}   gap ~{getattr(self.source, 'drops', 0)}\n"
                f"sat {getattr(self.source, 'sat', 0):6d}\n"
                f"band RMS (uV):\n{rms1}\n{rms2}")

        def closeEvent(self, event):
            self.timer.stop()
            try:
                self.worker.stop()
                self.thread.quit()
                self.thread.wait(2000)
            except Exception:
                pass
            try:
                self.plotter.close()
            except Exception:
                pass
            super().closeEvent(event)

    app = QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont("WenQuanYi Zen Hei", 9))
    win = MainWindow()
    win.show()
    return app.exec_()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default=None, help="UART port, e.g. /dev/ttyUSB0")
    ap.add_argument("--mode", default="test",
                    choices=["eeg", "diff", "test", "short"])
    ap.add_argument("--synthetic", action="store_true",
                    help="T2-like synthetic stream (no hardware)")
    ap.add_argument("--outdir", default=None,
                    help="write raw.bin/samples.csv/meta.json/SHA256SUMS")
    ap.add_argument("--label", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--screenshot", default=None)
    args = ap.parse_args()

    if args.synthetic or not args.port:
        source = SyntheticSource(outdir=args.outdir, label=args.label,
                                 note=args.note)
    else:
        source = UARTSource(args.port, args.mode, outdir=args.outdir,
                            label=args.label, note=args.note)
    sys.exit(run_app(source, screenshot=args.screenshot))


if __name__ == "__main__":
    main()
