import glob
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np
import pandas as pd

import widgets as w

# Teensy MTB DAQ log filenames are RTC-stamped: YYYYMMDD_HHMMSS.csv
_FILENAME_DATE_RE = re.compile(r"(\d{8})_\d{6}")


class FileManagerMixin:
    """Select Data tab: an in-tab folder browser that descends into
    directories and loads Teensy MTB DAQ ``.csv`` logs.

    Each row of the listbox is either a sub-directory (prefixed with a folder
    glyph) or a ``.csv`` file. Double-click a folder to descend; the "⬆ Up"
    button climbs to the parent. Selecting one or more files loads them.
    """

    def _populate_file_list(self):
        """List sub-folders then ``.csv`` files in the current directory."""
        try:
            names = os.listdir(self._source_dir)
        except OSError:
            names = []
        dirs = sorted(
            (n for n in names
             if os.path.isdir(os.path.join(self._source_dir, n)) and not n.startswith(".")),
            key=str.lower,
        )
        files = sorted(
            (os.path.basename(f) for f in
             glob.glob(os.path.join(self._source_dir, "*.csv")) +
             glob.glob(os.path.join(self._source_dir, "*.CSV"))),
            key=str.lower,
        )

        # Parallel list of (kind, abspath) aligned to listbox rows.
        self._entries = (
            [("dir", os.path.join(self._source_dir, d)) for d in dirs] +
            [("file", os.path.join(self._source_dir, f)) for f in files]
        )
        self._download_paths = [p for kind, p in self._entries if kind == "file"]

        self.file_listbox.delete(*self.file_listbox.get_children())
        idx = 0
        for d in dirs:
            self.file_listbox.insert("", tk.END, iid=str(idx),
                                     values=(f"📁 {d}", ""))
            idx += 1
        for f in files:
            fpath = os.path.join(self._source_dir, f)
            try:
                size_mb = f"{os.path.getsize(fpath)/1024/1024:.2f} MB"
            except OSError:
                size_mb = ""
            self.file_listbox.insert("", tk.END, iid=str(idx),
                                     values=(f, size_mb))
            idx += 1

        if hasattr(self, "_source_dir_var"):
            self._source_dir_var.set(self._source_dir)

    def refresh_file_list(self):
        """Re-scan the current source directory — picks up files added/removed
        (e.g. a new ride just offloaded from the SD card) without leaving the tab."""
        self._populate_file_list()

    def go_up_dir(self):
        parent = os.path.dirname(self._source_dir.rstrip(os.sep))
        if parent and parent != self._source_dir:
            self._source_dir = parent
            self._populate_file_list()

    def change_source_dir(self):
        directory = filedialog.askdirectory(title="Select Source Directory")
        if directory:
            self._source_dir = directory
            self._populate_file_list()

    def on_file_double_click(self, event):
        """Double-click a folder row to descend into it."""
        focused = self.file_listbox.focus()
        if not focused:
            return
        kind, path = self._entries[int(focused)]
        if kind == "dir":
            self._source_dir = path
            self._populate_file_list()

    def delete_selected_file(self):
        sel = [int(i) for i in self.file_listbox.selection()
               if self._entries[int(i)][0] == "file"]
        if not sel:
            messagebox.showwarning("No Selection", "Select a file to delete.")
            return
        paths = [self._entries[i][1] for i in sel]
        if len(paths) == 1:
            prompt = f"Permanently delete '{os.path.basename(paths[0])}'?"
        else:
            names = "\n".join(f"  • {os.path.basename(p)}" for p in paths)
            prompt = f"Permanently delete these {len(paths)} files?\n\n{names}"
        if not messagebox.askyesno("Confirm Delete", f"{prompt}\n\nThis cannot be undone."):
            return
        failed = []
        for p in paths:
            try:
                os.remove(p)
            except OSError as e:
                failed.append(f"{os.path.basename(p)}: {e.strerror}")
        self._populate_file_list()
        if failed:
            messagebox.showerror(
                "Delete Error",
                "Some files could not be deleted:\n\n" + "\n".join(failed))

    def on_file_select(self, event):
        # Debounced: a shift/ctrl multi-select drag fires <<TreeviewSelect>>
        # once per intermediate selection state, and each one used to trigger
        # a full reload+redraw — wasteful and part of why "just to preview"
        # felt slow. Wait for the selection to settle before actually loading.
        if getattr(self, "_file_select_job", None) is not None:
            self.after_cancel(self._file_select_job)
        self._file_select_job = self.after(150, self._on_file_select_settled)

    def _on_file_select_settled(self):
        self._file_select_job = None
        paths = [self._entries[int(i)][1] for i in self.file_listbox.selection()
                 if self._entries[int(i)][0] == "file"]
        if not paths:
            return
        # EventLog_* files are device event logs, not ride data — show them as a
        # wrapped table on the right instead of loading/plotting as a ride.
        eventlogs = [p for p in paths
                     if os.path.basename(p).lower().startswith("eventlog")]
        if eventlogs:
            self._show_eventlog(eventlogs[0])
            return
        self._show_preview_view()   # restore the plots view for ride CSVs
        dialog = w.ProgressDialog(self, "Loading ride data…")
        try:
            self._load_from_paths(paths, progress_cb=dialog.step)
        finally:
            dialog.close()

    @staticmethod
    def _parse_log_header(file_path):
        """Parse the self-describing ``#``-prefixed header block the Teensy
        logger writes (``writeHeader`` in sd_transfer). Structure:
            #MTB_DAQ,<format-version>     magic + schema version
            #CFG,<key>,<value>           one per config setting
            #COLUMNS                      next line is the column header
        Returns ``(config_dict, format_version)``. ``config_dict`` values are
        floats where parseable, else the raw string. Old logs without the block
        yield ``({}, None)``."""
        cfg, version = {}, None
        try:
            with open(file_path, "r", newline="") as f:
                for line in f:
                    line = line.rstrip("\r\n")
                    if line.startswith("#MTB_DAQ"):
                        parts = line.split(",")
                        version = parts[1].strip() if len(parts) > 1 else None
                    elif line.startswith("#CFG,"):
                        parts = line.split(",", 2)
                        if len(parts) >= 3:
                            key, val = parts[1].strip(), parts[2].strip()
                            try:
                                cfg[key] = float(val)
                            except ValueError:
                                cfg[key] = val
                    elif line.startswith("#COLUMNS"):
                        break
                    elif not line.startswith("#"):
                        break   # reached the data — no (further) header block
        except OSError:
            pass
        return cfg, version

    @staticmethod
    def _fast_time_to_timedelta(time_series):
        """Vectorized parse of the fixed-format 'HH:MM:SS.sss' time column
        (~12x faster than pd.to_timedelta for a 30-min/240Hz ride — was ~0.35s
        for 432k rows, the single largest cost in loading a file, per profiling).
        Bit-exact with pd.to_timedelta when taken (pure integer arithmetic, no
        float rounding — validated against it). Falls back to the original,
        slower, fully-general pd.to_timedelta parse — UNCHANGED, so behavior
        (incl. NaT on anything it can't parse) is identical — if any value
        doesn't match the exact 12-char shape, e.g. a row truncated by a
        power-loss mid-write."""
        try:
            raw = time_series.to_numpy(dtype="S12").view(np.uint8).reshape(-1, 12)
        except (ValueError, UnicodeEncodeError):
            return pd.to_timedelta(time_series.astype(str), errors="coerce")
        digit_positions = [0, 1, 3, 4, 6, 7, 9, 10, 11]
        shape_ok = (
            bool(np.all((raw[:, digit_positions] >= ord("0"))
                        & (raw[:, digit_positions] <= ord("9"))))
            and bool(np.all(raw[:, 2] == ord(":")))
            and bool(np.all(raw[:, 5] == ord(":")))
            and bool(np.all(raw[:, 8] == ord(".")))
        )
        if not shape_ok:
            return pd.to_timedelta(time_series.astype(str), errors="coerce")
        digit = (raw - ord("0")).astype(np.int64)
        hh  = digit[:, 0] * 10 + digit[:, 1]
        mm  = digit[:, 3] * 10 + digit[:, 4]
        ss  = digit[:, 6] * 10 + digit[:, 7]
        sss = digit[:, 9] * 100 + digit[:, 10] * 10 + digit[:, 11]
        total_ns = ((hh * 3600 + mm * 60 + ss) * 1000 + sss) * 1_000_000
        return pd.to_timedelta(total_ns, unit="ns")

    @staticmethod
    def _build_datetime_index(raw, file_path):
        """Combine the filename's YYYYMMDD date with the ``time`` column
        (HH:mm:ss.sss). The Teensy CSV stores time-of-day only — the date
        lives in the RTC-stamped filename. Handles a within-file midnight
        rollover by incrementing the day each time the clock steps backward."""
        m = _FILENAME_DATE_RE.search(os.path.basename(file_path))
        base_date = pd.to_datetime(m.group(1), format="%Y%m%d") if m else pd.Timestamp("2000-01-01")
        tod = FileManagerMixin._fast_time_to_timedelta(raw["time"].astype(str))
        rollover_days = (tod.diff() < pd.Timedelta(0)).cumsum()
        return base_date + tod + pd.to_timedelta(rollover_days, unit="D")

    def _load_from_paths(self, file_paths, progress_cb=None):
        """Load and process one or more ride CSVs. ``progress_cb(label, frac)``,
        if given, is called throughout — per file while reading (determinate,
        since we know file count up front) and passed on to the calibration
        cascade for its own checkpoints if the file carries a header."""
        def _progress(label, frac):
            if progress_cb:
                progress_cb(label, frac)

        # Reading + the calibration cascade below are weighted roughly by their
        # typical share of total time for a single mid-size ride; multi-file
        # loads spend proportionally more of it in the read loop.
        _READ_FRAC = 0.4

        # Import the self-describing config header (fork/shock cal, device name,
        # etc.) from the first file that carries one. comment="#" below skips the
        # block for the data read, so it must be parsed separately here.
        self._log_config = {}
        for file_path in file_paths:
            cfg, _ver = self._parse_log_header(file_path)
            if cfg:
                self._log_config = cfg
                break

        frames = []
        n = len(file_paths)
        for i, file_path in enumerate(file_paths):
            _progress(f"Reading {os.path.basename(file_path)} ({i+1}/{n})…",
                      _READ_FRAC * i / n)
            try:
                # comment="#" drops the header block + trailing "# ring_hwm=… " line.
                raw = pd.read_csv(file_path, comment="#", on_bad_lines="skip")
            except Exception as e:
                messagebox.showerror("Load Error", f"Could not read file:\n{e}")
                return
            if "time" in raw.columns:
                raw.index = self._build_datetime_index(raw, file_path)
                raw = raw.drop(columns=["time"]).sort_index()
                # Drop first 2 s of each file to allow sensor initialization
                if isinstance(raw.index, pd.DatetimeIndex) and len(raw) > 0:
                    raw = raw[raw.index >= raw.index[0] + pd.Timedelta(seconds=2)]
            frames.append(raw)

        if len(frames) > 1:
            combined = pd.concat(frames)
            if all(isinstance(f.index, pd.DatetimeIndex) for f in frames):
                combined = combined.sort_index()
        else:
            combined = frames[0]
        self.df = combined
        self.calibrated_df = self.df.copy()

        _progress("Refreshing signal lists…", _READ_FRAC)
        self._refresh_signal_lists()
        numeric_cols = list(self.df.select_dtypes(include="number").columns)
        if numeric_cols:
            self.cal_signal_combo.current(0)
            self.signal_listbox.selection_set(0)
            first = [numeric_cols[0]]
        else:
            first = []
        _progress("Drawing preview plots…", _READ_FRAC + 0.02)
        self.plot_signals(first)
        self.plot_histogram(first)
        self._update_cal_plots()
        self._auto_populate_calibrations()
        # Auto-update the fork/shock calibration rows from the imported header —
        # this is what actually runs the (slow) calibration cascade, so hand it
        # the remaining progress range.
        if self._log_config:
            _cal_cb = ((lambda label, frac: progress_cb(
                            label, _READ_FRAC + (1 - _READ_FRAC) * frac))
                       if progress_cb else None)
            self._apply_log_config_to_calibrations(self._log_config, progress_cb=_cal_cb)
        # Redraw the preview title now that the cascade has built the calibrated
        # wheel speeds — that's what the title's Distance readout integrates.
        self.plot_signals(first)
        _progress("Done", 1.0)

    def _refresh_signal_lists(self):
        numeric_cols = list(self.df.select_dtypes(include="number").columns)
        self.signal_listbox.delete(0, tk.END)
        for c in numeric_cols:
            self.signal_listbox.insert(tk.END, c)
        self.cal_signal_combo["values"] = numeric_cols
