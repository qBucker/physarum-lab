"""Read-only stall and sequence-gap watchdog for BCIkit soak runs.

Watches raw.bin growth every --interval seconds. If the file has not grown
for --stall-seconds, writes STALL_ALERT.txt (and beeps). With --csv, also
tails samples.csv incrementally and checks

  * the 8-bit OpenBCI sample number: a step > --step-threshold means samples
    were lost (the 2 h and 48 h soak runs showed single-sample gaps with
    step = 2, and one host-side burst with step = 205);
  * the host timestamp: a gap > --ts-gap seconds catches a host-side pause
    even when the sample counter happens to alias.

Sequence events are appended to GAP_ALERT.txt. The watchdog never opens the
serial port and never touches the recorder. If --pid is given, it exits
quietly when that recorder process exits, so a normal end of run does not
produce a false alarm.

Usage (Windows, started next to the recorder):

    python run_scripts/watchdog.py --file C:\\...\\raw.bin \\
        --csv C:\\...\\samples.csv --log C:\\...\\watchdog.csv \\
        --alert C:\\...\\STALL_ALERT.txt --gap-alert C:\\...\\GAP_ALERT.txt \\
        --pid <recorder pid>

The CSV log columns are:

    timestamp,size_bytes,growth_bytes,stalled_seconds,status,
    frames,seq_events,gap_samples,max_step,ts_events,max_ts_gap_s

`seq_events` counts every sample-number step >= 2 (missing samples);
`gap_samples` is the number of missing samples; `ts_events` counts host
timestamp gaps > --ts-gap. Only steps > --step-threshold and host gaps
raise GAP_ALERT.txt and beep.
"""

import argparse
import ctypes
import datetime
import os
import sys
import time

try:
    import winsound
except ImportError:  # non-Windows hosts are used for offline tests
    winsound = None

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if not hasattr(ctypes, "windll"):
        return True  # offline test host: no process probe
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


class GapMonitor:
    """Incremental reader for samples.csv.

    The recorder writes
    ``host_time_iso,host_unix,sample_number,ch1,...,ch8`` one row per frame.
    Only the first three fields are parsed. Bytes appended since the last
    poll are consumed; a trailing partial line is kept for the next poll.
    Data already present when the monitor is created is skipped, so a
    watchdog restart does not re-scan a large file.
    """

    def __init__(self, path, step_threshold=2, ts_gap=1.0):
        self.path = path
        self.step_threshold = step_threshold
        self.ts_gap = ts_gap
        self.pos = 0
        self.partial = b""
        self.prev_sample = None
        self.prev_ts = None
        self.frames = 0
        self.seq_events = 0
        self.gap_samples = 0
        self.max_step = 0
        self.ts_events = 0
        self.max_ts_gap = 0.0
        try:
            self.pos = os.path.getsize(path)
        except OSError:
            self.pos = 0

    def poll(self):
        """Consume new rows and return a list of alert event dicts."""
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size <= self.pos:
            return []
        with open(self.path, "rb") as fh:
            fh.seek(self.pos)
            chunk = fh.read(size - self.pos)
        self.pos += len(chunk)
        data = self.partial + chunk
        lines = data.split(b"\n")
        self.partial = lines.pop()  # incomplete trailing line
        events = []
        for line in lines:
            parts = line.split(b",", 3)
            if len(parts) < 3:
                continue
            try:
                ts = float(parts[1])
                sample = int(parts[2])
            except ValueError:
                continue  # header or malformed line
            if self.prev_sample is not None:
                step = (sample - self.prev_sample) % 256
                self.max_step = max(self.max_step, step)
                if step >= 2:
                    missing = step - 1
                    self.seq_events += 1
                    self.gap_samples += missing
                    if step > self.step_threshold:
                        events.append({
                            "kind": "sequence",
                            "sample_before": self.prev_sample,
                            "sample_after": sample,
                            "step": step,
                            "missing": missing,
                        })
            if self.prev_ts is not None:
                gap = ts - self.prev_ts
                self.max_ts_gap = max(self.max_ts_gap, gap)
                if gap > self.ts_gap:
                    self.ts_events += 1
                    events.append({
                        "kind": "host-time",
                        "gap_s": gap,
                        "unix_before": self.prev_ts,
                        "unix_after": ts,
                    })
            self.prev_sample = sample
            self.prev_ts = ts
            self.frames += 1
        return events

    def summary(self):
        return {
            "frames": self.frames,
            "seq_events": self.seq_events,
            "gap_samples": self.gap_samples,
            "max_step": self.max_step,
            "ts_events": self.ts_events,
            "max_ts_gap": self.max_ts_gap,
        }


def describe_event(event):
    if event["kind"] == "sequence":
        return ("sample {sample_before} -> {sample_after}: step {step}, "
                "{missing} sample(s) missing").format(**event)
    return "host timestamp gap {gap_s:.3f} s".format(**event)


def append_gap_alert(path, events):
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new_file:
            fh.write("SEQUENCE GAP ALERT\n")
        for event in events:
            fh.write(f"{now()}  {describe_event(event)}\n")
        fh.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--alert", required=True)
    ap.add_argument("--csv", default="",
                    help="samples.csv to tail for sequence/timestamp checks")
    ap.add_argument("--gap-alert", default="",
                    help="sequence alert file (default: GAP_ALERT.txt "
                         "next to --alert)")
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--stall-seconds", type=float, default=300.0)
    ap.add_argument("--step-threshold", type=int, default=2,
                    help="alert when a sample-number step exceeds this "
                         "(default 2: alert on >=2 missing samples)")
    ap.add_argument("--ts-gap", type=float, default=1.0,
                    help="alert when a host timestamp gap exceeds this many "
                         "seconds (default 1.0)")
    ap.add_argument("--beep-cooldown", type=float, default=60.0,
                    help="minimum seconds between sequence-alert beeps")
    ap.add_argument("--max-ticks", type=int, default=0,
                    help="stop after this many polls (0 = unlimited; for tests)")
    args = ap.parse_args()

    gap_alert = args.gap_alert
    if args.csv and not gap_alert:
        gap_alert = os.path.join(os.path.dirname(os.path.abspath(args.alert)),
                                 "GAP_ALERT.txt")
    monitor = GapMonitor(args.csv, args.step_threshold, args.ts_gap) \
        if args.csv else None

    last_size = -1
    last_growth = time.time()
    alerted = False
    last_beep = 0.0
    ticks = 0

    with open(args.log, "w", newline="") as fh:
        fh.write("timestamp,size_bytes,growth_bytes,stalled_seconds,status,"
                 "frames,seq_events,gap_samples,max_step,ts_events,"
                 "max_ts_gap_s\n")
        fh.flush()
        while True:
            if args.pid and not pid_alive(args.pid):
                fh.write(f"{now()},0,0,0,recorder-exited,0,0,0,0,0,0\n")
                fh.flush()
                break

            try:
                size = os.stat(args.file).st_size
            except FileNotFoundError:
                size = -1

            t = time.time()
            if size > last_size:
                growth = size - max(last_size, 0)
                last_size = size
                last_growth = t
                alerted = False
                status = "ok"
            else:
                growth = 0
                status = "no-growth"

            stalled = t - last_growth
            if stalled >= args.stall_seconds and not alerted:
                with open(args.alert, "w", encoding="utf-8") as ah:
                    ah.write("STALL ALERT\n")
                    ah.write(f"time: {now()}\n")
                    ah.write(f"file: {args.file}\n")
                    ah.write(f"size: {size}\n")
                    ah.write("last_growth: "
                             + datetime.datetime.fromtimestamp(last_growth)
                             .astimezone().isoformat(timespec="seconds") + "\n")
                    ah.write(f"stalled_seconds: {stalled:.0f}\n")
                if winsound is not None:
                    try:
                        for _ in range(3):
                            winsound.Beep(1200, 700)
                    except Exception:
                        pass
                status = "ALERT"
                alerted = True

            events = monitor.poll() if monitor is not None else []
            if events:
                append_gap_alert(gap_alert, events)
                status = "GAP" if status == "ok" else status + "+GAP"
                if winsound is not None and t - last_beep >= args.beep_cooldown:
                    try:
                        winsound.Beep(900, 500)
                    except Exception:
                        pass
                    last_beep = t

            if monitor is None:
                row = "0,0,0,0,0,0.0"
            else:
                s = monitor.summary()
                row = (f"{s['frames']},{s['seq_events']},{s['gap_samples']},"
                       f"{s['max_step']},{s['ts_events']},"
                       f"{s['max_ts_gap']:.6f}")
            fh.write(f"{now()},{size},{growth},{stalled:.0f},{status},{row}\n")
            fh.flush()

            ticks += 1
            if args.max_ticks and ticks >= args.max_ticks:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
