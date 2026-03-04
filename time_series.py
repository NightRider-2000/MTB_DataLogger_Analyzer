import tkinter as tk
from tkinter import ttk

import widgets as w
from constants import BG, DARK, HIST_COLORS

_N_PLOTS     = 3
_N_SIGS      = 3   # signals per plot
_ZOOM_FACTOR = 0.5
_PAN_FACTOR  = 0.2


class TimeSeriesMixin:

    def _build_time_series_tab(self):
        outer = tk.Frame(self.time_series_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=0)

        # ── Navigation buttons (top right) ────────────────────────────────────
        btn_bar = tk.Frame(outer, bg=BG)
        btn_bar.grid(row=0, column=0, sticky="e", padx=8, pady=4)
        for label, cmd in [
            ("◀◀",      self._ts_pan_left),
            ("Zoom In",  self._ts_zoom_in),
            ("Reset",    self._ts_reset),
            ("Zoom Out", self._ts_zoom_out),
            ("▶▶",      self._ts_pan_right),
        ]:
            w.make_btn(btn_bar, label, cmd).pack(side=tk.LEFT, padx=2)

        # ── Plot sections ─────────────────────────────────────────────────────
        # _ts_vars[plot][sig], _ts_combos[plot][sig]
        self._ts_vars        = []
        self._ts_combos      = []
        self._ts_axes        = []
        self._ts_figs        = []
        self._ts_canvases    = []
        self._ts_xlim_full    = None
        self._ts_xlim_current = None

        for i in range(_N_PLOTS):
            outer.rowconfigure(i + 1, weight=1)

            section = tk.Frame(outer, bg=BG)
            section.grid(row=i + 1, column=0, sticky="nsew", padx=6, pady=0)
            section.columnconfigure(0, weight=1)
            section.rowconfigure(1, weight=1)

            # Row of signal selectors (one per signal slot)
            sel_row = tk.Frame(section, bg=BG)
            sel_row.grid(row=0, column=0, sticky="ew", padx=4, pady=(2, 0))
            sel_row.columnconfigure(0, weight=1)

            inner_row = tk.Frame(sel_row, bg=BG)
            inner_row.grid(row=0, column=0)

            plot_vars   = []
            plot_combos = []
            for j in range(_N_SIGS):
                color_dot = tk.Label(inner_row, text="●", bg=BG,
                                     fg=HIST_COLORS[j % len(HIST_COLORS)], font=("", 11))
                color_dot.pack(side=tk.LEFT, padx=(6 if j else 0, 2))
                var   = tk.StringVar()
                combo = ttk.Combobox(inner_row, textvariable=var, state="readonly", width=22)
                combo.pack(side=tk.LEFT, padx=(0, 4))
                combo.bind("<<ComboboxSelected>>",
                           lambda e, pi=i: self._update_ts_plot(pi))
                plot_vars.append(var)
                plot_combos.append(combo)

            self._ts_vars.append(plot_vars)
            self._ts_combos.append(plot_combos)

            # Figure
            fig = w.make_figure(figsize=(10, 1.9), dpi=100)
            ax  = fig.add_subplot(111)
            ax.set_facecolor(BG)
            canvas, cv_widget = w.make_canvas(fig, section)
            cv_widget.grid(row=1, column=0, sticky="nsew")

            self._ts_figs.append(fig)
            self._ts_axes.append(ax)
            self._ts_canvases.append(canvas)

    # ── Signal population ─────────────────────────────────────────────────────

    def _refresh_ts_signals(self):
        if not hasattr(self, "_ts_combos"):
            return
        if self.cal_result_df is None:
            return
        cols = [""] + list(self.cal_result_df.columns)
        _defaults = {
            (0, 0): "Front_Wheel_Pos_perc",
            (0, 1): "Rear_Wheel_Pos_perc",
            (1, 0): "Front_Wheel_Spd_mph",
            (1, 1): "Rear_Wheel_Spd_mph",
            (1, 2): "Crank_Spd_rpm",
        }
        for i, plot_combos in enumerate(self._ts_combos):
            for j, combo in enumerate(plot_combos):
                current = combo.get()
                combo["values"] = cols
                if current and current in cols:
                    combo.set(current)
                else:
                    default = _defaults.get((i, j), "")
                    combo.set(default if default in cols else "")
            self._update_ts_plot(i)

    def _update_ts_plot(self, idx):
        if self.cal_result_df is None:
            return
        ax  = self._ts_axes[idx]
        fig = self._ts_figs[idx]

        ax.clear()
        ax.set_facecolor(BG)

        plotted = False
        for j, var in enumerate(self._ts_vars[idx]):
            col = var.get()
            if not col or col not in self.cal_result_df.columns:
                continue
            color = HIST_COLORS[j % len(HIST_COLORS)]
            series = w.insert_gap_nans(self.cal_result_df[[col]])[col]
            sparse = series.dropna()
            nan_frac = 1 - len(sparse) / max(len(series), 1)
            if nan_frac > 0.5:
                # Sparse signal (e.g. edge-detected RPM) — plot as dots
                ax.plot(sparse.index, sparse.values, color=color,
                        linestyle="none", marker=".", markersize=3)
            else:
                series.plot(ax=ax, legend=False, color=color)
            plotted = True

        if plotted:
            # Add a simple legend showing signal names with their colours
            handles = ax.get_lines()
            labels  = [var.get() for var in self._ts_vars[idx] if var.get()]
            if labels:
                ax.legend(handles[:len(labels)], labels,
                          fontsize=7, loc="upper right",
                          facecolor=BG, edgecolor=DARK, labelcolor=DARK)

            # Capture full range from data
            if self._ts_xlim_full is None:
                xlim = ax.get_xlim()
                if xlim[1] > xlim[0]:
                    self._ts_xlim_full    = xlim
                    self._ts_xlim_current = xlim

        ax.set_xlabel("Time" if idx == _N_PLOTS - 1 else "",
                      color=DARK, fontsize=8)
        w.style_ax(ax)

        if self._ts_xlim_current is not None:
            ax.set_xlim(self._ts_xlim_current)

        fig.tight_layout()
        self._ts_canvases[idx].draw()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _ts_set_xlim(self, xlim):
        self._ts_xlim_current = xlim
        for ax, canvas in zip(self._ts_axes, self._ts_canvases):
            ax.set_xlim(xlim)
            canvas.draw_idle()

    def _ts_zoom_in(self):
        lo, hi = self._ts_axes[0].get_xlim()
        mid  = (lo + hi) / 2
        half = (hi - lo) * (1 - _ZOOM_FACTOR) / 2
        self._ts_set_xlim((mid - half, mid + half))

    def _ts_zoom_out(self):
        lo, hi = self._ts_axes[0].get_xlim()
        mid  = (lo + hi) / 2
        half = (hi - lo) * (1 + _ZOOM_FACTOR) / 2
        if self._ts_xlim_full:
            full_lo, full_hi = self._ts_xlim_full
            lo_new = max(mid - half, full_lo)
            hi_new = min(mid + half, full_hi)
            self._ts_set_xlim((lo_new, hi_new))
        else:
            self._ts_set_xlim((mid - half, mid + half))

    def _ts_reset(self):
        if self._ts_xlim_full:
            self._ts_set_xlim(self._ts_xlim_full)

    def _ts_pan_left(self):
        lo, hi = self._ts_axes[0].get_xlim()
        shift = (hi - lo) * _PAN_FACTOR
        if self._ts_xlim_full:
            lo_new = max(lo - shift, self._ts_xlim_full[0])
            self._ts_set_xlim((lo_new, lo_new + (hi - lo)))
        else:
            self._ts_set_xlim((lo - shift, hi - shift))

    def _ts_pan_right(self):
        lo, hi = self._ts_axes[0].get_xlim()
        shift = (hi - lo) * _PAN_FACTOR
        if self._ts_xlim_full:
            hi_new = min(hi + shift, self._ts_xlim_full[1])
            self._ts_set_xlim((hi_new - (hi - lo), hi_new))
        else:
            self._ts_set_xlim((lo + shift, hi + shift))
