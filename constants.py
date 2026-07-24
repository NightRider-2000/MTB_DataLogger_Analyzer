# Global text scale — applied to Tk named fonts, matplotlib rcParams, and the
# explicit font-size literals (see theme.setup_theme + MTB_DataLog_Analyze).
FONT_SCALE  = 1.7
# Global additive point offset applied on top of FONT_SCALE everywhere text is
# sized. Every baked font-size literal is therefore round(base*FONT_SCALE)+FONT_DELTA.
FONT_DELTA  = -2

BG          = "#ffffff"
DARK        = "#1b3a6b"
FIELD       = "#a8b2bc"
BTN_FG      = "#ffffff"
GRID        = "#d0d8e0"
ROW_ALT     = "#bfc8d1"
TABLE_GRID  = "#808080"   # solid grey cell gridlines on every table (Treeview)
HIST_BAR_COLOR = "#1f3d7a"   # single-signal histogram line color (see widgets.plot_hist_line)
HIST_COLORS = ["#e05c2a", "#2a7be0", "#2ab55c", "#e0b82a", "#9b2ae0"]

# Histogram bin counts. Histograms are drawn as LINES (frequency polygons, not
# bars — widgets.plot_hist_line), so fewer bins than a bar chart read cleaner
# (a 200-bin line is jaggy). Tune here — every histogram references these.
HIST_BINS         = 120   # standard single-panel histograms
HIST_BINS_COMPACT = 90    # dense multi-signal panels (IMU groups)

# Semantic plot colors
TREND_COLOR        = "#e05c2a"   # orange    — regression/trend lines in scatter plots
BIN_MEAN_COLOR     = "#2a7be0"   # blue      — binned mean lines in scatter plots
SCATTER_ORIG_COLOR = "#888888"   # gray      — original/unaligned scatter series
TREND_ORIG_COLOR   = "#555555"   # dark gray — original/unaligned trend line
WORLD_AXIS_COLOR   = "#4488ff"   # blue      — ISO world-frame axes (IMU diagram)
BOARD_AXIS_COLOR   = "#111111"   # near-black — board-frame axes (IMU diagram)

# GPS tab
GPS_CMAP           = "jet"       # color scale for route + time-bar (blue→red; contrasts with green satellite)
GPS_START_COLOR    = "#1faa4d"   # green     — start (earlier) marker + map circle
GPS_FINISH_COLOR   = "#e23b2e"   # red       — finish (later) marker + map circle
GPS_TOPO_COLOR     = "#ffe08a"   # warm tan  — topographic contour lines over satellite

CAL_FIELDS  = ("Signal", "Calibrated_Name", "Raw_Sig_Min", "Raw_Sig_Max", "Value_at_Min", "Value_at_Max", "Bias", "Calibrated_Min", "Calibrated_Max")

# Auto-Filter Out Stopped Times (see calibration._compute_stopped_mask). The bike
# is "stopped" when the wheels aren't turning AND the rider isn't pedaling. GPS,
# suspension, and IMU are deliberately NOT used.
STOPPED_WHEEL_MPH = 0.5   # both wheel speeds at/below this (or NaN) = wheels not turning
STOPPED_CRANK_RPM = 5.0   # crank above this = pedaling → counts as moving (overrides wheels)
STOPPED_MIN_S     = 3.0   # enter-stopped: only stopped runs at least this long are filtered
STOPPED_RESUME_S  = 5.0   # exit-stopped: a stop only ends after this much SUSTAINED movement
                          # (brief moves shorter than this during a stop don't un-stop it;
                          #  the qualifying run reads as moving from its first sample)

# Auto-Filter Walking (see calibration._compute_walking_mask). The bike is being
# walked (not ridden) during a long continuous stretch of very slow wheel movement
# with the rear suspension near topout — slow, but no rider weight on the bike.
WALK_MAX_MPH        = 5.0    # centered-window-average wheel speed below this = very slow
WALK_SPEED_WIN_S    = 4.0    # total centered window (2 s each side) the speed is averaged over
WALK_REAR_COMP_PERC = 12.0   # Rear_Wheel_Pos_Perc below this = rear suspension uncompressed
WALK_MIN_S          = 8.0    # only continuous walking runs at least this long are filtered

# Gear selection gating (see calibration.py gear block). A gear is only
# determined during sustained pedaling — crank above GEAR_MIN_CRANK_RPM for at
# least GEAR_SUSTAIN_S continuously; elsewhere Gear_Selected is NaN (coasting/
# stopped: the chain isn't driving, so the crank/wheel ratio is meaningless).
GEAR_MIN_CRANK_RPM = 30.0
GEAR_SUSTAIN_S     = 3.0

# Susp Speed tab: shaded low-speed ↔ high-speed damping transition band, in
# damper SHAFT speed (mm/s) — the tab plots shaft speeds directly so this needs
# no motion-ratio conversion. Bounds per published tuning references (blow-off
# initiation ~150 mm/s ≈ 6 in/s; chosen upper anchor 300 mm/s); the true
# crossover is damper/adjuster dependent, hence a band, not a line.
SUSP_LSHS_BAND_MMPS = (150.0, 300.0)

# ── Filtered (Filt_) trend channels (calibration.py _filt / _apply_filt_channels)
# Zero-phase (forward-backward) low-pass that strips normal bumps and leaves the
# slow ride-height / attitude trend. It runs the dt-aware one-pole TWICE (forward
# then backward), which squares the magnitude response — so each pass is designed
# at FILT_PER_PASS_HZ to place the EFFECTIVE -3 dB at FILT_EFFECTIVE_HZ.
#   fc_pass = fc_eff / 0.644   (0.3 / 0.644 ≈ 0.466 Hz for a one-pole run twice)
FILT_EFFECTIVE_HZ = 0.3      # target combined (forward-backward) -3 dB cutoff
FILT_PER_PASS_HZ  = 0.466    # per-pass cutoff → ~0.3 Hz effective, zero-phase

# Signals that get an auto-generated Filt_<name> zero-phase twin by default.
# (User-selected 2026-07-20 — positions + load bias + attitude + body accel.)
FILT_SIGNALS = [
    "Front_Wheel_Pos_Perc",
    "Rear_Wheel_Pos_Perc",
    "Front_Load_Bias_Perc",
    "Pitch_deg",
    "Roll_deg",
    "aFwd_g",
    "aVert_g",
    "aLat_g",
]
