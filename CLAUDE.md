# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# MTB DataLogger Analyzer — Project Context

## Overview
Python/Tkinter desktop application for analyzing MTB data logger CSV files.

- **Entry point:** `MTB_DataLog_Analyze.py`
- **Run via:** `source .venv/bin/activate && python MTB_DataLog_Analyze.py`
- **venv:** `.venv/` using Homebrew Python 3.14 (system Python incompatible with macOS Tk)
- **GitHub:** https://github.com/NightRider-2000/MTB_DataLogger_Analyzer

## Module Structure
```
constants.py      — palette + CAL_FIELDS + HIST_COLORS
theme.py          — setup_theme(root)
widgets.py        — make_btn, make_entry, make_listbox, make_figure, make_canvas, style_ax, insert_gap_nans
file_manager.py   — FileManagerMixin
plots.py          — PlotsMixin
calibration.py    — CalibrationMixin
imu.py            — ImuMixin: IMU tab (histograms + bike/board images + axis diagram)
frequency.py      — FrequencyMixin
time_series.py    — TimeSeriesMixin
susp_speed.py     — SuspSpeedMixin
free_plot.py      — FreePlotMixin
sag.py            — SagMixin
bike_params.py    — BikeParamsMixin
device.py         — DeviceMixin: Device tab (USB serial → Teensy MTB protocol)
MTB_DataLog_Analyze.py — MountainBikeApp + __main__
```

## Dependencies
- `pyserial` — required for the Device tab (USB serial to Teensy). Install in venv: `pip install pyserial`
- `matplotlib`, `pandas`, `numpy`, `pillow` — standard data/plot stack

## Architecture
- Class: `MountainBikeApp(FileManagerMixin, PlotsMixin, CalibrationMixin, tk.Tk)`
- ttk theme: `clam` (required on macOS — Aqua ignores button bg colours)
- Window width: `self.winfo_screenwidth()` (full screen width), height 700
- Tab order: Device, Import Data, Bike Parameters, Calibration Parameters, IMU, Sag, Susp Speed, Time Series, Frequency, Free Scatter, Free Histogram (Device first so connection is the entry point)

## Key Patterns
- Widget factories in `widgets.py`: `make_btn`, `make_entry`, `make_listbox`, `make_figure`, `make_canvas`, `style_ax`
- Canvas widgets: `width=1, height=1` to let grid control size
- NavigationToolbar wrapped in frame (toolbar internally calls pack)
- `layout="constrained"` on `fig_hist`
- `insert_gap_nans(data, max_gap_s=1.0)` in widgets.py — inserts NaN rows at >1s gaps to break plot lines
- `autofill=False` when calling `_update_cal_plots` from treeview select

## Device Tab (device.py — DeviceMixin)
- Connection bar: Port dropdown, Refresh Ports, Baud combobox (default 115200; locked while connected), Connect/Disconnect
  - Teensy 4.1 USB CDC ignores the requested baud — the host setting only matters if the device-side firmware uses a HardwareSerial UART. Leave at 115200 unless you have a specific reason to change it
- Serial Dashboard: live ASCII feed from the Teensy `statusThread` (2 Hz), drained from a background reader thread into a `queue.Queue` and rendered via `after(80, _dev_poll_dashboard)`
- Teensy SD Files tree: `selectmode="extended"` for multi-select. macOS keys: ⌘-click toggle, ⇧-click range. Buttons: Select All, Clear Selection, ⬇ Download Selected, ✖ Cancel Download (enabled only during a transfer), 🗑 Delete Selected
- Host Files tree: shows `~/Documents/MTB_DAQ/Archived_Data/` with size + mtime
- Transfer status line: `Downloading <name> (i/N)  <bytes>/<total>  @ <speed>  ETA <m:ss>` — progress callback throttled to 10 Hz so the worker thread isn't starved by Tk's `after()` lock contention on macOS
- Cancel Download: sets a flag, calls `_serial.cancel_read()` to unblock pyserial, then force-disconnects (the Teensy will keep streaming the rest of the file and the protocol can't cleanly resync mid-transfer; user must reconnect)

## MTB Serial Protocol (device.py ↔ Teensy sd_transfer.cpp)
- ASCII command/response on USB CDC, with one exception: `MTB:GET` interleaves a raw binary block between `MTB:SIZE:<n>` and `MTB:CRC32:<hex>`
- Commands: `MTB:STATUS`, `MTB:LIST`, `MTB:GET:<name>`, `MTB:DEL:<name>`. All replies terminate with `MTB:END`
- Download integrity: the Teensy holds `_transferActive=true` for the whole duration including the trailing `MTB:CRC32` and `MTB:END` lines so the dashboard thread can't splice text into the binary stream or the CRC line. CRC32 verified on host via `zlib.crc32` (matches Teensy `crc32_update`); mismatch surfaces a popup but the file is still saved
- Device-side gating: the Teensy enters STANDBY automatically whenever USB is connected (host port open or charger active). In STANDBY, recording is stopped, the file is fully closed, and MTB commands work. There is no manual TRANSFER-mode button anymore

## CSV columns (current Teensy SW v21)
The CSV the device writes has a new `event` column at the end — a 0/1 spike that's `1` on the single row sampled right after the user pressed the secondary button (lap/jump marker). `file_manager.py` reads columns by name so new fields don't break import, but downstream tools that assume column count should be aware

## Speed Edge-Detection (calibration.py)
- Signals: `Crank_Spd_rpm` (A2mV), `Front_Horz_Wheel_Spd_mph` (A0mV), `Rear_Horz_Wheel_Spd_mph` (A1mV)
- Threshold: `raw.quantile(0.02) + (raw.quantile(0.98) - raw.quantile(0.02)) * 0.70` — hardcoded 70%
- After reindex: `.ffill(limit=20)` — holds last speed for up to 20 samples (~300ms)
- Falling-edge detection: `binary.diff() == -1`; dt = time for n_spokes edges = 1 revolution
- Series assignment: build `pd.Series(vals, index=DatetimeIndex(times))` then `.reindex(self.df.index)`
  — DO NOT use `series.loc[list] = vals`; fails when self.df.index has duplicate timestamps (multi-file concat)

## Documentation Rules
- Always update CLAUDE.md whenever architecture, module structure, key patterns, or data-processing behaviour changes
- CLAUDE.md must remain consistent with the source code at all times

## Code Style
- Partition logic heavily into small, focused sub-functions — avoid large monolithic functions
- Maximize reuse: if similar logic appears more than once, extract it into a shared helper
- Never use a companion "fresh" or "valid" boolean column alongside a data value — instead return NaN directly in the data field when the value is absent, stale, or invalid
- Always read the manufacturer datasheet for any interfaced hardware before writing configuration code — do not assume defaults or rely on library behaviour alone. Present all relevant configuration options to the user and confirm choices before implementing

## Key Constraints & Gotchas
- Use Homebrew Python (`.venv/`) — system Python on macOS is incompatible with Tkinter
- ttk theme must be `clam`, not `aqua` — Aqua theme ignores custom button background colours
- Multi-file load uses `pd.concat` + `sort_index`; duplicate timestamps are expected — do not drop them
- `series.loc[list] = vals` fails with duplicate DatetimeIndex — always use `.reindex()` pattern instead
- `insert_gap_nans` must be applied before plotting to prevent line segments bridging data gaps
- Tk `after(0, …)` from a non-main thread acquires Tk's lock — calling it from a worker every chunk of a serial download will starve the worker (sustained throughput collapses from MB/s to KB/s). Throttle UI updates from worker threads to ~10 Hz
