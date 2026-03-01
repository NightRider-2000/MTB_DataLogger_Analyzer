import matplotlib
matplotlib.use("TkAgg")   # must precede any matplotlib backend import

import os
import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from constants import BG, DARK
from theme import setup_theme
import widgets as w
from file_manager import FileManagerMixin
from plots import PlotsMixin
from calibration import CalibrationMixin


class MountainBikeApp(FileManagerMixin, PlotsMixin, CalibrationMixin, tk.Tk):

    # ── Init ─────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.title("MountainBike_Logger_Analysis")
        self.geometry("1200x700")
        self.configure(bg=BG)

        self.df                 = None
        self.calibrated_df      = None
        self.saved_calibrations = []
        self.cal_file_path      = None
        self._source_dir        = os.path.expanduser("~/Downloads")
        self._download_paths    = []

        setup_theme(self)
        self._build_ui()

    def _build_ui(self):
        nb = ttk.Notebook(self, style="App.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True)

        self.signals_tab = tk.Frame(nb, bg=BG)
        nb.add(self.signals_tab, text="Import Data")
        self._build_import_tab()

        self.calibration_tab = tk.Frame(nb, bg=BG)
        nb.add(self.calibration_tab, text="Calibration Settings")
        self._build_calibration_tab()

    # ── Import Data tab ──────────────────────────────────────────────────────
    def _build_import_tab(self):
        top = tk.Frame(self.signals_tab, bg=BG)
        top.pack(side=tk.TOP, fill=tk.X)
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
        file_sec.rowconfigure(1, weight=1)
        tk.Label(file_sec, text="Available Files:", bg=BG, fg=DARK).grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        self.file_listbox = w.make_listbox(file_sec, selectmode=tk.EXTENDED)
        self.file_listbox.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
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
        plots = tk.Frame(parent, bg=BG)
        plots.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        plots.columnconfigure(0, weight=1)
        plots.rowconfigure(0, weight=1)
        plots.rowconfigure(1, weight=1)
        plots.rowconfigure(2, weight=0)

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

        tb_frame = tk.Frame(plots, bg=BG)
        tb_frame.grid(row=2, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, tb_frame)
        self.toolbar.config(background=BG)
        self.toolbar.update()

    # ── Calibration Settings tab ─────────────────────────────────────────────
    def _build_calibration_tab(self):
        frame = tk.Frame(self.calibration_tab, bg=BG)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=3)
        frame.rowconfigure(7, weight=1)

        # Form: signal combo + entry fields
        form_rows = [
            ("Signal to calibrate",        None),
            ("Raw Signal Min",             "raw_min_entry"),
            ("Raw Signal Max",             "raw_max_entry"),
            ("Measured Value at Min",      "cal_min_entry"),
            ("Measured Value at Max",      "cal_max_entry"),
            ("Bias",                       "bias_entry"),
            ("New Calibrated Signal Name", "new_signal_entry"),
        ]
        for row, (label, attr) in enumerate(form_rows):
            tk.Label(frame, text=label, bg=BG, fg=DARK).grid(row=row, column=0, sticky="w")
            if attr is None:
                self.cal_signal_var   = tk.StringVar()
                self.cal_signal_combo = ttk.Combobox(frame, textvariable=self.cal_signal_var, state="readonly")
                self.cal_signal_combo.grid(row=row, column=1, padx=5, pady=5, sticky="we")
                self.cal_signal_combo.bind("<<ComboboxSelected>>", self._update_cal_plots)
            else:
                width  = 20 if attr == "new_signal_entry" else 10
                widget = w.make_entry(frame, width=width)
                widget.grid(row=row, column=1, sticky="w", padx=5, pady=2)
                widget.bind("<KeyRelease>", self._sync_form_to_table)
                setattr(self, attr, widget)

        # Saved calibrations treeview
        cols = ("Signal", "Raw Signal Min", "Raw Signal Max", "Measured Value at Min", "Measured Value at Max", "Bias", "New Calibrated Signal Name", "Calibrated Min", "Calibrated Max")
        self.cal_tree = ttk.Treeview(frame, columns=cols, show="headings", height=6)
        for col in cols:
            self.cal_tree.heading(col, text=col)
            width = 150 if col in ("Signal", "New Calibrated Signal Name") else 100
            self.cal_tree.column(col, width=width, anchor="center")
        self.cal_tree.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        self.cal_tree.bind("<<TreeviewSelect>>", self.on_cal_tree_select)

        # Persistence buttons
        persist = tk.Frame(frame, bg=BG)
        persist.grid(row=8, column=0, columnspan=2, pady=4, sticky="w")
        for text, cmd in [
            ("Load CSV", self.load_cal_file),
            ("Save CSV", self.save_cal_file),
        ]:
            w.make_btn(persist, text, cmd).pack(side=tk.LEFT, padx=5)

        # Preview: raw (top) + calibrated (middle) + calibrated histogram (bottom)
        cal_plot_frame = tk.Frame(frame, bg=BG)
        cal_plot_frame.grid(row=0, column=2, rowspan=10, padx=10, pady=5, sticky="nsew")
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
