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
HIST_BAR_COLOR = "#1f3d7a"
HIST_COLORS = ["#e05c2a", "#2a7be0", "#2ab55c", "#e0b82a", "#9b2ae0"]

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
