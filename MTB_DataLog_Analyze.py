import matplotlib
matplotlib.use("TkAgg")   # must precede any matplotlib backend import

import os
import tkinter as tk
from tkinter import ttk

from constants import FONT_SCALE, FONT_DELTA
# Scale matplotlib's base font size (relative sizes like 'large'/'medium' cascade
# from it). Explicit fontsize= calls in the plot modules are scaled at source.
matplotlib.rcParams["font.size"] = (
    matplotlib.rcParams["font.size"] * FONT_SCALE + FONT_DELTA)
# legend(loc=...) defaults to "best", which searches candidate positions against
# every plotted artist to avoid overlapping data — with a few hundred thousand
# points per axes (240 Hz rides) this alone took ~0.7s per legend, dominating
# tab-redraw time. A fixed corner is instant. Call sites whose corner would
# collide with a fixed on-axes annotation (e.g. a stats box) pass an explicit
# loc= to override this default — see those files for the specific corner.
matplotlib.rcParams["legend.loc"] = "upper right"

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from constants import BG, DARK, GRID, CAL_FIELDS
from theme import setup_theme
import widgets as w
from file_manager import FileManagerMixin
from plots import PlotsMixin
from calibration import CalibrationMixin
from bike_params import BikeParamsMixin
from sag import SagMixin
from susp_speed import SuspSpeedMixin
from free_plot import FreePlotMixin
from free_histogram import FreeHistogramMixin
from time_series import TimeSeriesMixin
from frequency import FrequencyMixin
from imu import ImuMixin
from gps import GpsMixin
from device import DeviceMixin


class MountainBikeApp(DeviceMixin, FileManagerMixin, PlotsMixin, CalibrationMixin, BikeParamsMixin, GpsMixin, SagMixin, SuspSpeedMixin, FreePlotMixin, FreeHistogramMixin, TimeSeriesMixin, FrequencyMixin, ImuMixin, tk.Tk):

    # ── Init ─────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.title("MountainBike_Logger_Analysis")
        # Start full-screen; size geometry to the full display as a fallback for
        # any platform where the -fullscreen attribute is ignored.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{screen_w}x{screen_h}+0+0")
        self.attributes("-fullscreen", True)
        # Esc exits full-screen so the user is never trapped without a title bar.
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self.configure(bg=BG)

        self.df                 = None
        self.calibrated_df      = None
        self.cal_result_df      = None
        self.saved_calibrations = []
        self.cal_file_path      = None
        self._log_config        = {}    # #CFG header block from the loaded CSV(s)
        self._source_dir        = os.path.expanduser("~/Documents/MTB_DAQ")
        self._download_paths    = []
        self._entries           = []

        setup_theme(self)
        self._build_ui()

        _default_cal = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "__UserFiles", "Calibration_Config", "Default_Calibration_Config.csv")
        if os.path.exists(_default_cal):
            try:
                self._load_cal_from_path(_default_cal)
            except Exception:
                pass

    def _build_ui(self):
        nb = ttk.Notebook(self, style="App.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True)

        self.device_tab = tk.Frame(nb, bg=BG)
        nb.add(self.device_tab, text="Device")
        self._build_device_tab()

        self.signals_tab = tk.Frame(nb, bg=BG)
        nb.add(self.signals_tab, text="Select Data")
        self._build_import_tab()

        self.bike_params_tab = tk.Frame(nb, bg=BG)
        nb.add(self.bike_params_tab, text="Bike Parameters")
        self._build_bike_params_tab()

        self.calibration_tab = tk.Frame(nb, bg=BG)
        nb.add(self.calibration_tab, text="Signal Calibration")
        self._build_calibration_tab()

        self.gps_tab = tk.Frame(nb, bg=BG)
        nb.add(self.gps_tab, text="GPS")
        self._build_gps_tab()

        self.imu_tab = tk.Frame(nb, bg=BG)
        nb.add(self.imu_tab, text="IMU")
        self._build_imu_tab()

        self.sag_tab = tk.Frame(nb, bg=BG)
        nb.add(self.sag_tab, text="Sag")
        self._build_sag_tab()

        self.susp_speed_tab = tk.Frame(nb, bg=BG)
        nb.add(self.susp_speed_tab, text="Susp Speed")
        self._build_susp_speed_tab()

        self.time_series_tab = tk.Frame(nb, bg=BG)
        nb.add(self.time_series_tab, text="Time Series")
        self._build_time_series_tab()

        self.frequency_tab = tk.Frame(nb, bg=BG)
        nb.add(self.frequency_tab, text="Frequency")
        self._build_frequency_tab()

        self.free_plot_tab = tk.Frame(nb, bg=BG)
        nb.add(self.free_plot_tab, text="Free Scatter")
        self._build_free_plot_tab()

        self.free_histogram_tab = tk.Frame(nb, bg=BG)
        nb.add(self.free_histogram_tab, text="Free Histogram")
        self._build_free_histogram_tab()

    # ── Import Data tab ──────────────────────────────────────────────────────
    def _build_import_tab(self):
        top = tk.Frame(self.signals_tab, bg=BG)
        top.pack(side=tk.TOP, fill=tk.X)
        w.make_btn(top, "Refresh File List",       self.refresh_file_list).pack(side=tk.LEFT, padx=5, pady=5)
        w.make_btn(top, "⬆ Up",                    self.go_up_dir).pack(side=tk.LEFT, padx=5, pady=5)
        w.make_btn(top, "Change Source Directory", self.change_source_dir).pack(side=tk.LEFT, padx=5, pady=5)
        w.make_btn(top, "Delete File",             self.delete_selected_file).pack(side=tk.LEFT, padx=5, pady=5)

        center = tk.Frame(self.signals_tab, bg=BG)
        center.pack(fill=tk.BOTH, expand=True)
        center.columnconfigure(0, weight=1)
        center.columnconfigure(1, weight=4)
        center.rowconfigure(0, weight=1)

        self._build_left_panel(center)
        self._build_plots_panel(center)

    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        # Available files (top half)
        file_sec = tk.Frame(left, bg=BG)
        file_sec.grid(row=0, column=0, sticky="nsew")
        file_sec.columnconfigure(0, weight=1)
        file_sec.rowconfigure(2, weight=1)
        tk.Label(file_sec, text="Available Files (double-click a 📁 folder to open):", bg=BG, fg=DARK).grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        self._source_dir_var = tk.StringVar(value=self._source_dir)
        tk.Label(file_sec, textvariable=self._source_dir_var,
                 bg=BG, fg=GRID, font=("TkFixedFont", 12),
                 anchor="w", wraplength=0).grid(
            row=1, column=0, sticky="ew", padx=5, pady=(0, 2))
        file_tree_frame = tk.Frame(file_sec, bg=BG)
        file_tree_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        file_tree_frame.rowconfigure(0, weight=1)
        file_tree_frame.columnconfigure(0, weight=1)
        self.file_listbox = ttk.Treeview(
            file_tree_frame, columns=("name", "size"),
            show="headings", selectmode="extended")
        self.file_listbox.heading("name", text="Name")
        self.file_listbox.heading("size", text="Size")
        self.file_listbox.column("name", width=240, stretch=True)
        self.file_listbox.column("size", width=110, minwidth=90, anchor="e",
                                 stretch=False)
        w.enable_gridlines(self.file_listbox)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        file_vsb = ttk.Scrollbar(file_tree_frame, orient=tk.VERTICAL,
                                 command=self.file_listbox.yview)
        file_vsb.grid(row=0, column=1, sticky="ns")
        self.file_listbox.configure(yscrollcommand=file_vsb.set)
        self.file_listbox.bind("<<TreeviewSelect>>", self.on_file_select)
        self.file_listbox.bind("<Double-Button-1>", self.on_file_double_click)
        self._populate_file_list()

        # Signal selector (bottom half)
        sig_sec = tk.Frame(left, bg=BG)
        sig_sec.grid(row=1, column=0, sticky="nsew")
        sig_sec.columnconfigure(0, weight=1)
        sig_sec.rowconfigure(1, weight=1)
        tk.Label(sig_sec, text="Plot Raw Signal:", bg=BG, fg=DARK).grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        self.signal_listbox = w.make_listbox(sig_sec)
        self.signal_listbox.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.signal_listbox.bind("<<ListboxSelect>>", self.on_signal_select)

    def _build_plots_panel(self, parent):
        # Just a quick overview of the loaded data — no zoom/pan/save toolbar;
        # a plain time-series + histogram is enough for a glance at a ride.
        plots = tk.Frame(parent, bg=BG)
        plots.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        plots.columnconfigure(0, weight=1)
        plots.rowconfigure(0, weight=1)
        plots.rowconfigure(1, weight=1)

        self.fig = w.make_figure(figsize=(8, 3), dpi=100)
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_facecolor(BG)
        self.canvas, cv_widget = w.make_canvas(self.fig, plots)
        self.canvas.draw()
        cv_widget.grid(row=0, column=0, sticky="nsew")

        self.fig_hist = w.make_figure(figsize=(8, 3), dpi=100, layout="constrained")
        self.ax_hist  = self.fig_hist.add_subplot(111)
        self.ax_hist.set_facecolor(BG)
        self.canvas_hist, hist_widget = w.make_canvas(self.fig_hist, plots)
        hist_widget.grid(row=1, column=0, sticky="nsew")

    # ── Calibration Settings tab ─────────────────────────────────────────────
    def _build_calibration_tab(self):
        frame = tk.Frame(self.calibration_tab, bg=BG)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=3)
        frame.rowconfigure(8, weight=1)

        # Action bar — the ONLY way form edits take effect. Nothing below
        # recomputes or redraws automatically on keystroke; edits sit in the
        # form until this button is pressed.
        action_bar = tk.Frame(frame, bg=BG)
        action_bar.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        w.make_btn(action_bar, "Apply Updates",
                   self.apply_calibration_updates).pack(side=tk.LEFT, padx=(0, 12))
        w.make_btn(action_bar, "Auto-Cal Fork (Zero Min)",
                   self.auto_calibrate_fork).pack(side=tk.LEFT, padx=(0, 6))
        w.make_btn(action_bar, "Auto-Cal Shock (Zero Min)",
                   self.auto_calibrate_shock).pack(side=tk.LEFT, padx=(0, 6))

        # Form: signal combo + entry fields. Editing these does nothing on its
        # own — click "Apply Updates" above to commit and recompute.
        form_rows = [
            ("Signal to calibrate",        None),
            ("Raw Signal at Min",             "raw_min_entry"),
            ("Raw Signal at Max",             "raw_max_entry"),
            ("Calibrated Value at Min",    "cal_min_entry"),
            ("Calibrated Value at Max",    "cal_max_entry"),
            ("Bias",                       "bias_entry"),
            ("New Calibrated Signal Name", "new_signal_entry"),
        ]
        for row, (label, attr) in enumerate(form_rows, start=1):
            tk.Label(frame, text=label, bg=BG, fg=DARK).grid(row=row, column=0, sticky="w")
            if attr is None:
                self.cal_signal_var   = tk.StringVar()
                self.cal_signal_combo = ttk.Combobox(frame, textvariable=self.cal_signal_var, state="readonly", width=20)
                self.cal_signal_combo.grid(row=row, column=1, padx=5, pady=5, sticky="w")
                self.cal_signal_combo.bind("<<ComboboxSelected>>", self._update_cal_plots)
            elif attr == "new_signal_entry":
                _cal_names = [
                    "Fork_Pos_mm", "Shock_Pos_mm", "Batt_SoC", "Board_Temp_C",
                    "aX_g", "aY_g", "aZ_g", "gX_DPS", "gY_DPS", "gZ_DPS",
                    "Front_Horz_Wheel_Spd_mph", "Rear_Horz_Wheel_Spd_mph", "Crank_Spd_RPM",
                    "BLE_Power_W", "BLE_Cadence_RPM",
                ]
                widget = ttk.Combobox(frame, values=_cal_names, state="readonly", width=20)
                widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                setattr(self, attr, widget)
            else:
                widget = w.make_entry(frame, width=20)
                widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                setattr(self, attr, widget)

        # Saved calibrations treeview. ttk Treeview headings can't wrap text
        # onto 2 lines (embedded "\n" is drawn as a single line regardless of
        # heading-row height — confirmed, not a styling issue) — so headers
        # are short, no-underscore abbreviations that fit on one line instead.
        col_defs = [
            ("Signal",          "Signal",   90),
            ("Calibrated_Name", "Cal. Name", 110),
            ("Raw_Sig_Min",     "Raw Min",   85),
            ("Raw_Sig_Max",     "Raw Max",   85),
            ("Value_at_Min",    "Val Min",   80),
            ("Value_at_Max",    "Val Max",   80),
            ("Bias",            "Bias",      60),
            ("Calibrated_Min",  "Cal Min",   90),
            ("Calibrated_Max",  "Cal Max",   90),
        ]
        # col_id_order must match CAL_FIELDS exactly for positional value alignment
        col_id_order = list(CAL_FIELDS)
        self.cal_tree = ttk.Treeview(frame, columns=col_id_order, show="headings", height=6)
        self.cal_tree["displaycolumns"] = [d[0] for d in col_defs]
        for col_id, col_text, col_width in col_defs:
            self.cal_tree.heading(col_id, text=col_text)
            self.cal_tree.column(col_id, width=col_width, minwidth=col_width, anchor="center")
        w.enable_gridlines(self.cal_tree)

        tree_scroll = ttk.Scrollbar(frame, orient="horizontal", command=self.cal_tree.xview)
        self.cal_tree.configure(xscrollcommand=tree_scroll.set)
        self.cal_tree.grid(row=8, column=0, columnspan=2, padx=5, pady=(5, 0), sticky="nsew")
        tree_scroll.grid(row=9, column=0, columnspan=2, padx=5, sticky="ew")
        self.cal_tree.bind("<<TreeviewSelect>>", self.on_cal_tree_select)

        # Persistence buttons
        persist = tk.Frame(frame, bg=BG)
        persist.grid(row=10, column=0, columnspan=2, pady=4, sticky="w")
        for text, cmd in [
            ("Load CSV", self.load_cal_file),
            ("Save CSV", self.save_cal_file),
        ]:
            w.make_btn(persist, text, cmd).pack(side=tk.LEFT, padx=5)

        # Preview: raw (top) + calibrated (middle) + calibrated histogram (bottom)
        cal_plot_frame = tk.Frame(frame, bg=BG)
        cal_plot_frame.grid(row=0, column=2, rowspan=11, padx=10, pady=5, sticky="nsew")
        self.fig_cal      = w.make_figure(figsize=(4, 7), dpi=100)
        self.ax_raw_cal   = self.fig_cal.add_subplot(311)
        self.ax_raw_cal.set_facecolor(BG)
        self.ax_cal       = self.fig_cal.add_subplot(312)
        self.ax_cal.set_facecolor(BG)
        self.ax_hist_cal  = self.fig_cal.add_subplot(313)
        self.ax_hist_cal.set_facecolor(BG)
        self.canvas_cal   = FigureCanvasTkAgg(self.fig_cal, master=cal_plot_frame)
        self.canvas_cal.draw()
        self.canvas_cal.get_tk_widget().pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    app = MountainBikeApp()
    app.mainloop()
