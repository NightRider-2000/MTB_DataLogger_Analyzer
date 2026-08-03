import os
import warnings
import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd

import widgets as w
from constants import (BG, DARK, FIELD, ROW_ALT, TABLE_GRID, BTN_FG,
                       HIST_BAR_COLOR, HIST_COLORS, GRID, HIST_BINS)

# EventLog table: fixed pixel widths for the short columns (the "message" column
# flexes + wraps to fill the rest); friendlier header titles. Unknown columns
# fall back to a default width and a title-cased header.
_EVTLOG_COL_W = {
    "datetime": 155, "soc_pct": 60, "temp_c": 65,
    "device_state": 135, "charger_state": 95, "usb_state": 80,
}
_EVTLOG_TITLES = {
    "datetime": "Datetime", "soc_pct": "SoC %", "temp_c": "Temp °C",
    "device_state": "Device State", "charger_state": "Charger",
    "usb_state": "USB", "message": "Message",
}
_EVTLOG_DEFAULT_W = 100

# Distance integration: an inter-sample gap longer than this (s) is a
# file-boundary / firmware pause, not continuous travel — its interval is
# dropped so it can't inject a bogus speed×gap distance.
_DIST_GAP_MAX_S = 1.0


class PlotsMixin:

    def on_signal_select(self, event):
        if self.df is None:
            return
        selected = [self.signal_listbox.get(i) for i in self.signal_listbox.curselection()]
        self.plot_signals(selected)
        self.plot_histogram(selected)

    # ── EventLog tabular view (right panel, shown for EventLog_* files) ─────────

    def _build_eventlog_view(self, parent):
        """A wrapped, scrollable table view that replaces the preview plots when
        an EventLog_ file is selected. Built once, hidden until needed."""
        view = tk.Frame(parent, bg=BG)
        view.grid(row=0, column=0, sticky="nsew")
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)
        self._eventlog_view = view

        self._eventlog_title = tk.Label(view, bg=BG, fg=DARK, anchor="w",
                                        font=("TkDefaultFont", 15, "bold"))
        self._eventlog_title.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        holder = tk.Frame(view, bg=TABLE_GRID, highlightbackground=DARK,
                          highlightthickness=1)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.rowconfigure(1, weight=1)   # canvas row flexes; header row (0) fixed
        holder.columnconfigure(0, weight=1)

        # Frozen header row — lives OUTSIDE the scrolled canvas so it stays put.
        # Same column config + width as the body grid, so columns line up.
        header = tk.Frame(holder, bg=TABLE_GRID)
        header.grid(row=0, column=0, sticky="ew")
        self._eventlog_header = header

        canvas = tk.Canvas(holder, bg=FIELD, highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=canvas.yview)
        vsb.grid(row=1, column=1, sticky="ns")   # aligned with the canvas only
        canvas.configure(yscrollcommand=vsb.set)
        self._eventlog_canvas = canvas

        # Grid of wrapping Labels over a TABLE_GRID background — 1-px cell gaps
        # give the gridlines (ttk.Treeview can't wrap; same pattern as the Device
        # Config editor). No horizontal scroll: the message column wraps to fill.
        grid = tk.Frame(canvas, bg=TABLE_GRID)
        self._eventlog_grid = grid
        self._eventlog_win = canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", self._eventlog_on_canvas_configure)
        self._eventlog_msg_labels = []
        self._eventlog_fixed_w = 0

        view.grid_remove()   # hidden until an EventLog_ file is selected

    def _eventlog_on_canvas_configure(self, event):
        # Stretch the grid to the canvas width and wrap the message column into
        # whatever horizontal space is left after the fixed columns.
        self._eventlog_canvas.itemconfigure(self._eventlog_win, width=event.width)
        msg_w = max(180, event.width - self._eventlog_fixed_w - 12)
        for lbl in self._eventlog_msg_labels:
            lbl.configure(wraplength=msg_w)

    def _show_preview_view(self):
        """Show the time-series + histogram preview (ride CSVs); hide EventLog."""
        if getattr(self, "_eventlog_view", None) is not None:
            self._eventlog_view.grid_remove()
        if getattr(self, "_preview_view", None) is not None:
            self._preview_view.grid()

    def _show_eventlog(self, path):
        """Load an EventLog_ CSV and show it as a wrapped table (no plotting)."""
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False,
                             skipinitialspace=True)
        except Exception as e:
            messagebox.showerror("Event Log", f"Could not read event log:\n{e}")
            return
        self._eventlog_title.configure(
            text=f"Event Log — {os.path.basename(path)}   ({len(df)} rows)")
        self._populate_eventlog_table(df)
        if getattr(self, "_preview_view", None) is not None:
            self._preview_view.grid_remove()
        self._eventlog_view.grid()

    def _populate_eventlog_table(self, df):
        header, grid = self._eventlog_header, self._eventlog_grid
        for f in (header, grid):
            for child in f.winfo_children():
                child.destroy()
            for c in range(f.grid_size()[0]):
                f.columnconfigure(c, weight=0, minsize=0)
        self._eventlog_msg_labels = []
        cols = list(df.columns)

        def _scroll(e):
            self._eventlog_canvas.yview_scroll(-e.delta, "units")

        # Column config is applied IDENTICALLY to the frozen header and the body
        # grid, and both are stretched to the same width, so their columns align.
        fixed_w = 0
        for c, col in enumerate(cols):
            is_msg = (col.lower() == "message")
            width = _EVTLOG_COL_W.get(col, _EVTLOG_DEFAULT_W)
            title = _EVTLOG_TITLES.get(col, col.replace("_", " ").title())
            for f in (header, grid):
                f.columnconfigure(c, weight=1 if is_msg else 0,
                                  minsize=(180 if is_msg else width))
            if not is_msg:
                fixed_w += width
            hlbl = tk.Label(header, text=title, bg=DARK, fg=BTN_FG, font="TableFont",
                            wraplength=(400 if is_msg else width - 8),
                            justify="left", anchor="w", padx=4, pady=2)
            hlbl.grid(row=0, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
            hlbl.bind("<MouseWheel>", _scroll)
        self._eventlog_fixed_w = fixed_w

        for r in range(len(df)):
            row_bg = FIELD if r % 2 == 0 else ROW_ALT
            for c, col in enumerate(cols):
                is_msg = (col.lower() == "message")
                width = _EVTLOG_COL_W.get(col, _EVTLOG_DEFAULT_W)
                lbl = tk.Label(grid, text=str(df.iat[r, c]), bg=row_bg, fg=DARK,
                               font="TableFont",
                               wraplength=(400 if is_msg else width - 8),
                               justify="left", anchor="nw", padx=4, pady=2)
                lbl.grid(row=r, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
                lbl.bind("<MouseWheel>", _scroll)
                if is_msg:
                    self._eventlog_msg_labels.append(lbl)

        # Wrap the message column to the current width right away.
        self._eventlog_canvas.update_idletasks()
        cw = self._eventlog_canvas.winfo_width()
        if cw > 1:
            msg_w = max(180, cw - fixed_w - 12)
            for lbl in self._eventlog_msg_labels:
                lbl.configure(wraplength=msg_w)
        self._eventlog_canvas.yview_moveto(0.0)

    def _ride_distance_mi(self):
        """Total distance (miles) over the WHOLE recording (all loaded files),
        integrating the NaN-mean of the front & rear wheel speeds (mph) over
        time. Uses the UNfiltered full frame (`_cal_full`) so it's the true
        total regardless of the stopped/walking/GPS view filters. Inter-file /
        pause gaps are dropped (see _DIST_GAP_MAX_S). Returns None when the
        calibrated wheel speeds aren't available (e.g. header-less log before
        Apply Updates)."""
        import numpy as np
        df = getattr(self, "_cal_full", None)
        if df is None:
            df = getattr(self, "cal_result_df", None)
        if (df is None or df.empty
                or not isinstance(df.index, pd.DatetimeIndex)):
            return None
        cols = [c for c in ("Front_Horz_Wheel_Spd_mph", "Rear_Horz_Wheel_Spd_mph")
                if c in df.columns]
        if not cols:
            return None
        avg_mph = df[cols].mean(axis=1, skipna=True).to_numpy()   # NaN-mean F/R
        dt_s = df.index.to_series().diff().dt.total_seconds().to_numpy()
        dt_s = np.where(np.isfinite(dt_s) & (dt_s <= _DIST_GAP_MAX_S), dt_s, 0.0)
        avg_mph = np.where(np.isfinite(avg_mph), avg_mph, 0.0)
        return float(np.sum(avg_mph * dt_s / 3600.0))   # mph × hours = miles

    def plot_signals(self, columns):
        self.ax.clear()
        self.ax.set_facecolor(BG)
        if not columns or self.df is None:
            self.ax.set_title("No data / no signals selected", color=DARK)
            self.canvas.draw()
            return
        # Per-column, not one bulk DataFrame.plot() call — sparse raw signals
        # (GPS fixes, trigger-driven wheel speed: >90% NaN) need dot markers
        # or a connected line is either invisible or misleadingly continuous.
        for i, col in enumerate(columns):
            w.plot_time_series_smart(self.ax, self.df[col],
                                     color=HIST_COLORS[i % len(HIST_COLORS)], label=col)
        # Always pin the x-axis to the ride's real time range — an all-NaN
        # signal otherwise leaves matplotlib's default 0..1 axis in place,
        # which renders as garbled dates on a datetime axis.
        self.ax.set_xlim(self.df.index.min(), self.df.index.max())
        if self.df[columns].isna().all().all():
            self.ax.text(0.5, 0.5, "No Data Available", transform=self.ax.transAxes,
                         ha="center", va="center", color=DARK, fontsize=14)
        elif len(columns) > 1:
            self.ax.legend(fontsize=10, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
        title = "Time Series (raw)"
        if "rtcDate" in self.df.columns:
            date_val = self.df["rtcDate"].dropna().max()
            if date_val is not None:
                title += f"  —  {date_val}"
        try:
            duration_min = (self.df.index.max() - self.df.index.min()).total_seconds() / 60
            dist = self._ride_distance_mi()
            dist_str = f"    Distance: {dist:.2f} mi" if dist is not None else ""
            title = f"Duration: {duration_min:.2f} min{dist_str}\n{title}"
        except Exception:
            pass
        self.ax.set_title(title, color=DARK)
        self.ax.set_xlabel("Time", color=DARK)
        self.ax.set_ylabel("Value", color=DARK)
        w.style_ax(self.ax)
        w.format_time_axis(self.ax)
        self.fig.autofmt_xdate()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig.tight_layout()
        self.canvas.draw()

    def plot_histogram(self, columns):
        self.ax_hist.clear()
        self.ax_hist.set_facecolor(BG)
        if not columns or self.df is None:
            self.ax_hist.set_title("Select a signal", color=DARK)
            w.style_ax(self.ax_hist)
            self.canvas_hist.draw()
            return

        # Gather valid signals, then bin every overlaid histogram on the SAME
        # edges (rule: 2+ histograms on one Axes share bins — see plot_hist_line).
        pairs = [(c, self.df[c].dropna()) for c in columns]
        pairs = [(c, d) for c, d in pairs if not d.empty]
        edges = (w.shared_bin_edges([d.values for _, d in pairs], HIST_BINS)
                 if pairs else HIST_BINS)
        stats_lines = []
        for i, (col, data) in enumerate(pairs):
            color = HIST_BAR_COLOR
            mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
            w.plot_hist_line(self.ax_hist, data, edges, color=color, label=col)
            self.ax_hist.axvline(mean, color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
            self.ax_hist.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvspan(mean - std, mean + std, alpha=0.12, color=color)
            stats_lines.append(
                f"{col}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}"
            )

        if stats_lines:
            self.ax_hist.text(
                0.97, 0.97, "\n\n".join(stats_lines),
                transform=self.ax_hist.transAxes, fontsize=10,
                verticalalignment="top", horizontalalignment="right", color=DARK,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9),
            )
        else:
            self.ax_hist.text(0.5, 0.5, "No Data Available",
                              transform=self.ax_hist.transAxes,
                              ha="center", va="center", color=DARK, fontsize=14)
        self.ax_hist.set_title("Histogram", color=DARK)
        self.ax_hist.set_xlabel("Value", color=DARK)
        self.ax_hist.set_ylabel("Count", color=DARK)
        if len(columns) > 1:
            # upper left: the stats box above occupies upper right
            self.ax_hist.legend(fontsize=10, loc="upper left")
        w.style_ax(self.ax_hist)
        self.canvas_hist.draw()
