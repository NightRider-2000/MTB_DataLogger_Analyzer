# MTB DataLogger Analyzer

A Python/Tkinter desktop application for loading, calibrating, and visualizing
mountain-bike suspension + chassis data recorded by the custom **Teensy 4.1 MTB
DAQ** logger (fork/shock displacement, wheel & crank speed, IMU attitude, GPS,
optional BLE power). Logs are 240 Hz CSV files with a self-describing header.

> Private repository. The detailed engineering/architecture notes live in
> **`CLAUDE.md`**; this README is the overview.

## Tabs / features

- **Device** — Connect to the Teensy MTB DAQ over USB; browse/download SD-card
  files; upload/edit the on-device `CONFIG.CSV`; live serial dashboard.
- **Select Data** — Load one or more ride CSVs (single or concatenated). Raw
  signal time-series + histogram preview, with a title readout of **Duration**
  and **Distance** (miles, from the NaN-mean of the front/rear wheel speeds over
  the whole recording). Default-on **auto-filters** for stopped time and walking,
  each with a live "N s (P%)" readout. Selecting an **`EventLog_*.csv`** shows it
  as a wrapped, scrollable **table** (frozen header) instead of plots.
- **Bike Parameters** — Titled, boxed card-tables: **Suspension** (spring rate /
  preload / fork-shock travel / vertical wheel travel), **Bike Geometry** (head-
  tube angle, wheel base, chainstay, front center [= wheelbase − chainstay], BB
  height, IMU pitch offset), **Drivetrain & Wheels**, **Rear Suspension Motion
  Ratio** (editable table + CSV load/save + **Leverage Ratio plot**), and
  **Cassette Gears**.
- **Signal Calibration** — Map raw signals to engineering units with a linear
  calibration. **Edits apply only on the "Apply Updates" button** (nothing
  recomputes on keystroke). Fork/shock zero-min bias is auto-computed on load.
  Save/load calibration configs as CSV.
- **GPS** — Satellite basemap with the ride route colored by any signal, topo
  contour overlay, draggable time-window scrubber, and slippy-map pan/zoom.
- **IMU** — Attitude (pitch/roll/yaw, ISO 8855), body accel, and gyro histograms;
  bike photo + board axis-orientation diagram.
- **Sag** — Dynamic sag for front and rear, in both wheel travel and shaft stroke.
- **Susp Speed** — Compression vs. rebound **shaft-speed** histograms (front &
  rear, 95th-percentile-scaled, x-linked) plus **position-vs-shaft-speed 2D
  histograms** (fork/shock) with a shaded LS↔HS damping-transition band.
- **Time Series** — 6 stacked, synchronized plots, 4 signals each; per-signal
  **left/right Y-axis** assignment via framed toggle buttons; left-of-plot
  marginal histograms. Shows the **full** ride and shades the stopped/walking
  regions in transparent red (the histograms exclude those samples).
- **Frequency** — Two panes: overlaid PSDs of up to 3 signals, and a PSD-vs-X
  "order analysis" map (speed or time). Opt-in compute button.
- **Free Scatter** — Any two calibrated signals as an X–Y scatter with trend line
  + binned mean; optional color axis; "Time (s)" selectable on any axis.
- **Free Histogram** — Overlay signals as histograms with per-signal stats; 2D
  density (heat map) when a Y axis is selected.

## Derived / calibrated signals (computed automatically)

| Signal | Description |
|---|---|
| `Fork_Pos_mm` / `Shock_Pos_mm` | Linear calibration of the raw suspension voltage (auto from the CSV `#CFG` header) |
| `Fork_Pos_Perc` / `Shock_Pos_Perc` | Shaft stroke as % of fork/shock travel |
| `Front_/Rear_Wheel_Pos_mm` | Vertical wheel travel (fork·sin(HTA); shock via motion-ratio LUT) |
| `Front_/Rear_Wheel_Pos_Perc` | Vertical wheel travel as % of max |
| `Front_/Rear_Wheel_Air` | 1 when the wheel is at ≤ 9 % travel (off the ground) |
| `Fork_/Shock_Shaft_Spd_mmps` | Shaft velocity (Savitzky-Golay derivative) — what the damper circuits see |
| `Front_/Rear_Vert_Wheel_Spd_mmps` | Vertical wheel velocity |
| `Front_/Rear_Horz_Wheel_Spd_mph` | Wheel speed from the frequency channels (chatter-despiked) |
| `Crank_Spd_RPM` | Crank cadence |
| `Gear_Selected` | Nearest cassette gear during sustained pedaling (NaN while coasting) |
| `aFwd_g` / `aVert_g` / `aLat_g` | IMU accel rotated into ISO 8855 (X-fwd, Y-left, Z-up) |
| `gRoll_/gPitch_/gYaw_DPS` | IMU gyro rates in ISO 8855 |
| `Pitch_deg` / `Roll_deg` / `Yaw_deg` | Attitude from the SFLP quaternion (ISO 8855) |
| `Fork_/Shock_Load_N`, `Front_/Rear_Vert_Load_N`, `Front_Load_Bias_Perc`, `Pedal_Only_Ref_Bias_Perc` | Spring-only tire-load model + front/rear balance — **proprietary, see `model_ip.py`** |
| `Filt_<name>` | Zero-phase (forward-backward, ~0.3 Hz) low-pass trend twin of selected signals |
| `Batt_SoC`, `gps_spd_mph`, `Board_Temp_C` | Battery SoC, GPS ground speed (mph), IMU die temp |
| `Stopped` / `Walking` | 0/1 auto-filter state flags |

## Note on proprietary code

`model_ip.py` (the spring-force / load-distribution model) is flagged as
**potential IP**. Because this repo is private it's committed, but it's kept
isolated for easy separation later: the `_ip.py` filename + `_IP` function
suffixes are grep markers, and it's imported behind a `_HAS_MODEL_IP` guard so
the app runs fine without it (those channels just aren't produced). To make the
repo public, pull `model_ip.py` out and re-add `*_ip.py` to `.gitignore`.

## Setup

### Requirements
- Python 3.11+ (tested on 3.14 via Homebrew — macOS *system* Python is not
  Tkinter-compatible). macOS, Windows, or Linux with a display.

### Install
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pandas matplotlib pillow scipy pyserial
```

### Run
```bash
source .venv/bin/activate
python MTB_DataLog_Analyze.py
```
(Or `./run.sh`.)

## User files
Place these under `__UserFiles/` before first run:

| File | Purpose |
|---|---|
| `Bike_Picture.jpeg` | Bike image on the Bike Parameters / IMU tabs |
| `Calibration_Config/Default_Calibration_Config.csv` | Auto-loaded calibration on startup |
| `Bike_Config/Default_Rear_Susp_Motion_Ratio.csv` | Default rear motion-ratio lookup |

## Input format — Teensy MTB DAQ CSV (240 Hz)
Ride files begin with a self-describing `#`-prefixed header
(`#MTB_DAQ,<ver>` magic, one `#CFG,key,value` per config setting, then
`#COLUMNS` before the `time,...` column header). The fork/shock `#CFG` cal
values auto-populate the calibration table on load. Plain CSV readers skip the
`#` block. Time-of-day is in the `time` column; the date comes from the
`YYYYMMDD_HHMMSS_<device>.csv` filename. (The old OpenLog-Artemis `.TXT` format
is no longer supported.)

## Motion-ratio CSV format
```
Shock_Travel,Wheel_Vertical_Travel
0.0,0
1.91,6
...
```

## Project structure
```
MTB_DataLog_Analyze.py   — App entry point + UI layout
constants.py             — Palette, field definitions, filter/model constants
theme.py                 — ttk theme setup
widgets.py               — Shared widget/figure factory functions
file_manager.py          — File loading, folder browser, auto-filter plumbing
plots.py                 — Select Data preview + EventLog table view
calibration.py           — Calibration + all derived-signal computation
model_ip.py              — Proprietary spring-force / load model (flagged potential IP)
bike_params.py           — Bike Parameters tab (geometry, motion ratio, cassette)
device.py                — Device tab (USB serial ↔ Teensy MTB DAQ)
gps.py                   — GPS tab (satellite route map + time window)
basemap.py               — Satellite + DEM tile fetch/stitch
imu.py                   — IMU tab (attitude/accel/gyro + axis diagram)
sag.py                   — Sag tab
susp_speed.py            — Susp Speed tab (shaft-speed histograms + 2D maps)
time_series.py           — Time Series tab (6 plots, axis toggle, filter shading)
frequency.py             — Frequency tab (PSD + order-analysis map)
free_plot.py             — Free Scatter tab
free_histogram.py        — Free Histogram tab
__UserFiles/             — User-supplied config + image files
```

## Hardware
Designed for the custom **Teensy 4.1 MTB DAQ** logger (LSM6DSV16X IMU with
on-chip SFLP fusion, u-blox MAX-M10S GPS, Honeywell SPS suspension pots,
inductive wheel/crank sensors, optional nRF52840 BLE power-meter bridge). See
the `Teensy_MTB_DAQ` firmware repo for the device side.
