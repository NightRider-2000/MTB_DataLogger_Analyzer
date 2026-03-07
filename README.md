# MTB DataLogger Analyzer

A desktop application for loading, calibrating, and visualizing mountain bike suspension data recorded by an OpenLog Artemis (OLA) data logger.

## Features

- **Import Data** — Load one or more OLA `.TXT` log files; view raw signal time series and histograms
- **Bike Parameters** — Enter fork/shock travel, wheel circumference, spoke counts, head tube angle, and rear suspension motion ratio (editable table + CSV import/export)
- **Calibration Parameters** — Map raw ADC signals to engineering units with a linear calibration; live preview updates on every keystroke; save/load calibration configs as CSV
- **Sag** — Visualize dynamic sag for front and rear suspension, both wheel displacement and suspension stroke.
- **Susp Speed** — Compression vs. rebound speed histograms (front and rear) plus a front vs. rear scatter plot with a 1:1 reference line and linear trend
- **Time Series** — Three stacked, synchronized plots; zoom and pan controls; configurable signal selection per plot
- **Free Plot** — Freely choose any two calibrated signals for an X–Y scatter or time series overlay

## Derived signals computed automatically

| Signal | Description |
|---|---|
| `Fork_Pos_mm` / `Shock_Pos_mm` | Linear calibration of raw potentiometer ADC |
| `Front_Wheel_Pos_mm` / `Rear_Wheel_Pos_mm` | Travel in mm (HTA projection for fork; motion-ratio LUT for shock) |
| `Front_Wheel_Pos_perc` / `Rear_Wheel_Pos_perc` | Travel as % of max travel |
| `Front_Wheel_Air` / `Rear_Wheel_Air` | Binary flag — 1 when suspension is at ≤9 % travel (wheel off ground) |
| `Front_Horz_Wheel_Spd_mph` / `Rear_Horz_Wheel_Spd_mph` | Wheel speed from falling-edge detection on rotor spoke signal |
| `Crank_Spd_rpm` | Crank RPM from falling-edge detection on chain-ring spoke signal |
| `Front_Vert_Wheel_Spd_mmPs` / `Rear_Vert_Wheel_Spd_mmPs` | Suspension velocity (mm/s) from differentiated position |
| `Board_SoC` | Battery state of charge (linear calibration) |

## Setup

### Requirements

- Python 3.11+ (tested on 3.14 via Homebrew — macOS system Python is not compatible with Tkinter)
- macOS, Windows, or Linux with a display

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pandas matplotlib pillow
```

### Run

```bash
source .venv/bin/activate
python MTB_DataLog_Analyze.py
```

## User files

Place the following files in the `__UserFiles/` directory before first run:

| File | Purpose |
|---|---|
| `Bike_Picture.jpeg` | Bike image shown on the Bike Parameters tab |
| `Calibration_Config/Default_Calibration_Config.csv` | Auto-loaded calibration on startup |
| `Bike_Config/Default_Rear_Susp_Motion_Ratio.csv` | Default rear suspension motion ratio lookup table |

## Calibration CSV format

```
Signal,raw_min,raw_max,cal_min,cal_max,bias,new_signal_name,cal_result_min,cal_result_max
analog_4,0,4095,0,160,0,Fork_Pos_mm,,
```

## Motion ratio CSV format

```
Shock_Travel,Wheel_Vertical_Travel
0.0,0
1.91,6
...
```

## Project structure

```
MTB_DataLog_Analyze.py   — App entry point + UI layout
constants.py             — Colour palette and field definitions
theme.py                 — ttk theme setup
widgets.py               — Shared widget/figure factory functions
file_manager.py          — File loading and signal list management
calibration.py           — Calibration logic and derived signal computation
bike_params.py           — Bike Parameters tab (motion ratio, geometry inputs)
sag.py                   — Sag tab
susp_speed.py            — Suspension Speed tab
time_series.py           — Time Series tab
free_plot.py             — Free Plot tab
plots.py                 — Raw signal plotting helpers
__UserFiles/             — User-supplied config and image files
```

## Screenshots

**Import Data** — Load one or more log files; browse raw signals and view histograms with mean/σ overlays.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%2012.43.28%20PM.png)

**Sag** — Suspension stroke histograms showing dynamic sag distribution for front and rear.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%201.12.08%20PM.png)

**Free Plot** — Arbitrary X–Y scatter or time-series overlay of any two calibrated signals; colour axis optional.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%202.38.39%20PM.png)

**Frequency** — Power spectral density of any calibrated signal.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%202.49.18%20PM.png)

**Calibration Parameters** — Map raw ADC counts to engineering units with live plot preview.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%203.04.27%20PM.png)

**IMU** — Attitude (pitch/roll/yaw), ISO accelerometer, and ISO gyro histograms; bike photo and board axis diagram.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%203.04.37%20PM.png)

**Bike Parameters** — Fork/shock travel, wheel geometry, cassette tooth counts, and rear suspension motion-ratio curve.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%204.25.27%20PM.png)

**Time Series** — Three stacked, synchronised plots with zoom/pan controls and configurable signal selection.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%204.51.57%20PM.png)

**Susp Speed** — Compression/rebound speed histograms plus front vs. rear scatter with dynamic wheelbase time-alignment (green = aligned, gray = original) and 20-bin mean ±1σ bands.

![](__UserFiles/ScreenShots/Screenshot%202026-03-07%20at%205.42.15%20PM.png)

## Hardware

Designed for data logged by the [SparkFun OpenLog Artemis](https://www.sparkfun.com/products/16832) at high sample rates. Log files are standard CSV exported as `.TXT`.
