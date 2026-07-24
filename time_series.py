import tkinter as tk
from tkinter import ttk

import widgets as w
from constants import BG, DARK, FIELD, HIST_COLORS, HIST_BINS

_N_PLOTS     = 6   # stacked plots (page scrolls vertically to reach them all)
_N_SIGS      = 4   # signals per plot
_SECTION_H   = 200 # MINIMUM plot-section height (px); actual height is set dynamically so
                   # exactly 3 sections fill the viewport (see _on_canvas_configure)
_SECTION_PAD = 4   # vertical padding below each section (must match its pack pady)
_ZOOM_FACTOR = 0.5
_PAN_FACTOR  = 0.2

# Per-slot signal colors: red, blue, yellow, green (slots 0-3). Each signal's
# y-axis is selectable via a framed arrow BUTTON above the plot — ◀ = left
# (primary), ▶ = right (secondary); click to toggle. The right axis auto-scales
# independently so a very-different-range signal can share the plot. DEFAULT is
# slots 0-2 → left, slot 3 (green) → right (unchanged from before). Only
# LEFT-axis signals get a marginal histogram.
_TS_COLORS   = [HIST_COLORS[0], HIST_COLORS[1], HIST_COLORS[3], HIST_COLORS[2]]  # red, blue, yellow, green


class TimeSeriesMixin:

    def _build_time_series_tab(self):
        outer = tk.Frame(self.time_series_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Navigation buttons (top right, FIXED above the scroll area) ───────
        btn_bar = tk.Frame(outer, bg=BG)
        btn_bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)
        btn_wrap = tk.Frame(btn_bar, bg=BG)
        btn_wrap.pack()   # centered horizontally in the fill-X bar
        for label, cmd in [
            ("◀◀",      self._ts_pan_left),
            ("Zoom In",  self._ts_zoom_in),
            ("Reset",    self._ts_reset),
            ("Zoom Out", self._ts_zoom_out),
            ("▶▶",      self._ts_pan_right),
        ]:
            w.make_btn(btn_wrap, label, cmd).pack(side=tk.LEFT, padx=2)

        # ── Vertically-scrollable area holding the plot sections ──────────────
        # Canvas + inner frame + scrollbar. Each section has a FIXED height
        # (pack_propagate off) so the total content is taller than the viewport
        # and the canvas scrolls; mouse-wheel is bound only while the pointer is
        # over the area (so it doesn't fight other tabs' scroll handlers).
        scroll_wrap = tk.Frame(outer, bg=BG)
        scroll_wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scroll_canvas = tk.Canvas(scroll_wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_wrap, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        plots_frame = tk.Frame(scroll_canvas, bg=BG)
        _win = scroll_canvas.create_window((0, 0), window=plots_frame, anchor="nw")
        plots_frame.bind("<Configure>",
                         lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))

        def _on_canvas_configure(e):
            scroll_canvas.itemconfigure(_win, width=e.width)
            # Size each section so exactly 3 fill the viewport height (each keeps
            # its selectors + x-tick labels). Re-runs on any window resize.
            h = max(_SECTION_H, (e.height - 3 * _SECTION_PAD) // 3)
            for sec in self._ts_sections:
                sec.configure(height=h)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)

        def _on_wheel(e):
            scroll_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        scroll_canvas.bind("<Enter>", lambda e: scroll_canvas.bind_all("<MouseWheel>", _on_wheel))
        scroll_canvas.bind("<Leave>", lambda e: scroll_canvas.unbind_all("<MouseWheel>"))
        self._ts_scroll_canvas = scroll_canvas

        # ── Plot sections ─────────────────────────────────────────────────────
        # _ts_vars[plot][sig], _ts_combos[plot][sig]
        self._ts_vars        = []
        self._ts_combos      = []
        self._ts_axis_side   = []   # per-slot y-axis "L"/"R" (framed toggle buttons)
        self._ts_axis_btns   = []   # the framed arrow buttons themselves
        self._ts_axes        = []
        self._ts_axes2       = []   # secondary (right) y-axis per plot (twinx)
        self._ts_hist_axes   = []   # marginal histogram axis (left of each plot, shares the value scale)
        self._ts_figs        = []
        self._ts_canvases    = []
        self._ts_sections    = []   # plot-section frames (height set dynamically so 3 fit)
        self._ts_xlim_full    = None
        self._ts_xlim_current = None

        for i in range(_N_PLOTS):
            section = tk.Frame(plots_frame, bg=BG, height=_SECTION_H)
            section.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, _SECTION_PAD))
            section.pack_propagate(False)   # keep the set height so the area scrolls
            self._ts_sections.append(section)

            # Row of signal selectors (one per signal slot)
            sel_row = tk.Frame(section, bg=BG)
            sel_row.pack(side=tk.TOP, fill=tk.X, padx=4)
            inner_row = tk.Frame(sel_row, bg=BG)
            inner_row.pack()

            plot_vars   = []
            plot_combos = []
            plot_sides  = []
            plot_btns   = []
            for j in range(_N_SIGS):
                color = _TS_COLORS[j % len(_TS_COLORS)]
                side  = "R" if j == _N_SIGS - 1 else "L"   # default: last slot → right
                # Framed, clickable button whose colored triangle shows this
                # signal's y-axis (◀ left / ▶ right); click toggles it.
                axis_btn = tk.Label(inner_row, text=("▶" if side == "R" else "◀"),
                                    bg=FIELD, fg=color, font=("", 13, "bold"),
                                    relief="raised", bd=2, padx=4, cursor="hand2")
                axis_btn.pack(side=tk.LEFT, padx=(6 if j else 0, 2))
                axis_btn.bind("<Button-1>",
                              lambda e, pi=i, sj=j: self._ts_toggle_axis(pi, sj))
                var   = tk.StringVar()
                combo = ttk.Combobox(inner_row, textvariable=var, state="readonly", width=22)
                combo.pack(side=tk.LEFT, padx=(0, 4))
                combo.bind("<<ComboboxSelected>>",
                           lambda e, pi=i: self._update_ts_plot(pi))
                plot_vars.append(var)
                plot_combos.append(combo)
                plot_sides.append(side)
                plot_btns.append(axis_btn)

            self._ts_vars.append(plot_vars)
            self._ts_combos.append(plot_combos)
            self._ts_axis_side.append(plot_sides)
            self._ts_axis_btns.append(plot_btns)

            # Figure — a narrow marginal HISTOGRAM (left) + the time series (right),
            # side by side sharing the value scale (the histogram bins line up with
            # the plot's y-axis). Fills the remaining section height.
            fig = w.make_figure(figsize=(10, 2.0), dpi=100)
            ax_hist, ax = fig.subplots(
                1, 2, gridspec_kw={"width_ratios": [1, 6], "wspace": 0.03})
            ax.set_facecolor(BG)
            ax_hist.set_facecolor(BG)
            ax2 = ax.twinx()   # secondary right y-axis for the last signal slot
            ax2.set_facecolor("none")
            canvas, cv_widget = w.make_canvas(fig, section)
            cv_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

            self._ts_figs.append(fig)
            self._ts_axes.append(ax)
            self._ts_axes2.append(ax2)
            self._ts_hist_axes.append(ax_hist)
            self._ts_canvases.append(canvas)

    # ── Signal population ─────────────────────────────────────────────────────

    def _refresh_ts_signals(self):
        if not hasattr(self, "_ts_combos"):
            return
        if self.cal_result_df is None:
            return
        # Reset x-axis limits so they are recalculated from the new data
        self._ts_xlim_full    = None
        self._ts_xlim_current = None
        cols = [""] + list(self.cal_result_df.columns)
        _defaults = {
            # Plot 0 (top) — speeds
            (0, 0): "Front_Horz_Wheel_Spd_mph",
            (0, 1): "Rear_Horz_Wheel_Spd_mph",
            (0, 2): "gps_spd_mph",
            # Plot 1 — crank cadence + gear (gear on the far-right slot = the
            # secondary right axis, so its 1-12 range auto-scales apart from RPM)
            (1, 2): "Crank_Spd_RPM",
            (1, 3): "Gear_Selected",
            # Plot 2 — suspension position % + front load bias
            (2, 0): "Front_Wheel_Pos_Perc",
            (2, 1): "Rear_Wheel_Pos_Perc",
            (2, 2): "Front_Load_Bias_Perc",
            # Plot 3 — chassis attitude
            (3, 0): "Roll_deg",
            (3, 1): "Pitch_deg",
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
        ax2 = self._ts_axes2[idx]   # secondary right y-axis — for the last signal slot
        fig = self._ts_figs[idx]

        ax.clear();  ax.set_facecolor(BG)
        ax2.clear(); ax2.set_facecolor("none")

        handles, labels = [], []
        right_colors = []
        for j, var in enumerate(self._ts_vars[idx]):
            col = var.get()
            if not col or col not in self.cal_result_df.columns:
                continue
            color  = _TS_COLORS[j % len(_TS_COLORS)]
            is_sec = (self._ts_axis_side[idx][j] == "R")   # right (secondary) axis?
            target = ax2 if is_sec else ax
            w.plot_time_series_smart(target, self.cal_result_df[col], color=color)
            handles.append(target.get_lines()[-1])
            labels.append(col)
            if is_sec:
                right_colors.append(color)

        if labels:
            # Draw the legend on the SECONDARY axis: it's the twinx drawn last, so
            # it renders on top — otherwise the 4th (secondary) signal's dots cover
            # a legend placed on the primary axis.
            leg = ax2.legend(handles, labels, fontsize=10, loc="upper right",
                             facecolor=BG, edgecolor=DARK, labelcolor=DARK)
            leg.set_zorder(20)
            # Capture full range from data (primary axis carries the shared x).
            if self._ts_xlim_full is None:
                xlim = ax.get_xlim()
                if xlim[1] > xlim[0]:
                    self._ts_xlim_full    = xlim
                    self._ts_xlim_current = xlim

        # Each plot is independent in the scroll list, so every one carries its
        # own HH:MM:SS.mmm time tick labels (no single shared "bottom" axis).
        w.style_ax(ax)
        w.format_time_axis(ax)
        self._ts_style_secondary(ax2, right_colors)

        if self._ts_xlim_current is not None:
            ax.set_xlim(self._ts_xlim_current)   # ax2 shares x via twinx
        # Fit each y-axis to the data visible in the current x-window (independent
        # scales — that's the whole point of the secondary axis).
        self._ts_autoscale_y(ax)
        self._ts_autoscale_y(ax2)
        # The value scale lives on the histogram (far left); the time series shares
        # it, so hide its own y tick labels.
        ax.tick_params(axis="y", labelleft=False)
        # Marginal histogram of the primary signals over the visible window.
        self._ts_draw_hist(idx)

        # left = room for the histogram's value labels; right = secondary axis labels.
        fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.24, wspace=0.03)
        self._ts_canvases[idx].draw()

    def _ts_draw_hist(self, idx):
        """Marginal histogram to the LEFT of the time series: the distribution of
        each PRIMARY-axis signal (slots 0-2; the 4th/secondary-axis signal is
        excluded since it has a different scale), over only the data visible in the
        current x-window, binned along the shared value (y) axis so the bins line
        up with the plot's y-axis. Recomputed on every draw and every pan/zoom."""
        import numpy as np
        ax  = self._ts_axes[idx]
        axh = self._ts_hist_axes[idx]
        axh.clear()
        axh.set_facecolor(BG)
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        meds = []   # (color, median) per primary signal, over the visible window
        if y1 > y0:
            edges   = np.linspace(y0, y1, HIST_BINS + 1)
            centers = 0.5 * (edges[:-1] + edges[1:])
            for line in ax.get_lines():          # primary-axis lines only (not ax2)
                xd = np.asarray(line.get_xdata(orig=False), dtype=float)
                yd = np.asarray(line.get_ydata(orig=False), dtype=float)
                if xd.size == 0:
                    continue
                m = (xd >= x0) & (xd <= x1) & np.isfinite(yd)
                if not m.any():
                    continue
                counts, _ = np.histogram(yd[m], bins=edges)          # shared bins (y-range)
                axh.plot(counts, centers, color=line.get_color(), linewidth=1.5)
                meds.append((line.get_color(), float(np.median(yd[m]))))
        axh.set_ylim(y0, y1)                     # match the time series value scale
        w.style_ax(axh)
        axh.invert_xaxis()                       # counts grow leftward, away from the plot
        axh.tick_params(axis="x", labelbottom=False)   # count magnitude isn't labeled
        # Median markers + color-coded value labels (over the visible window),
        # stacked at the top so they stay legible even when the medians are close.
        for k, (color, med) in enumerate(meds):
            axh.axhline(med, color=color, linestyle="--", linewidth=1.0, alpha=0.7, zorder=1)
            axh.text(0.5, 0.97 - k * 0.12, f"med {med:.3g}", transform=axh.transAxes,
                     color=color, fontsize=8, ha="center", va="top", fontweight="bold")

    @staticmethod
    def _ts_style_secondary(ax2, right_colors):
        """Style / show the secondary right y-axis. Hidden when no signal is
        assigned to it (so an empty 0–1 right axis never shows); colored to that
        signal when exactly one is on it (preserving the old single-signal look),
        neutral DARK when it carries several."""
        if not right_colors:
            ax2.yaxis.set_visible(False)
            ax2.spines["right"].set_visible(False)
            return
        col = right_colors[0] if len(right_colors) == 1 else DARK
        ax2.yaxis.set_visible(True)
        ax2.spines["right"].set_visible(True)
        ax2.spines["right"].set_color(col)
        ax2.tick_params(axis="y", colors=col)
        ax2.grid(False)   # keep only the primary axis' gridlines

    def _ts_toggle_axis(self, pi, sj):
        """Flip a signal slot between the left (primary) and right (secondary)
        y-axis when its framed arrow button is clicked. Updates the ◀/▶ glyph and
        redraws; only left-axis signals get a marginal histogram."""
        new = "R" if self._ts_axis_side[pi][sj] == "L" else "L"
        self._ts_axis_side[pi][sj] = new
        self._ts_axis_btns[pi][sj].configure(text=("▶" if new == "R" else "◀"))
        self._update_ts_plot(pi)

    # ── Navigation ────────────────────────────────────────────────────────────

    @staticmethod
    def _ts_autoscale_y(ax):
        """Fit the y-axis to only the data visible within the axis' current
        x-window, across every line on the plot. Lets the y-range tighten as you
        zoom/pan in x instead of staying stretched to the whole ride. The axis
        floats to the visible data's true min/max (with a 5% pad) — so it
        auto-zooms **even when that min is > 0**; it is never anchored at zero."""
        import numpy as np
        x0, x1 = ax.get_xlim()
        ymin, ymax = np.inf, -np.inf
        for line in ax.get_lines():
            # orig=False → the numeric (date-number) x-data actually used by the
            # axis, so it compares directly against get_xlim(). get_xdata() returns
            # datetime objects, which would mismatch the axis' float date-numbers.
            xd = np.asarray(line.get_xdata(orig=False), dtype=float)
            yd = np.asarray(line.get_ydata(orig=False), dtype=float)
            if xd.size == 0 or xd.size != yd.size:
                continue
            m = (xd >= x0) & (xd <= x1) & np.isfinite(yd)
            if m.any():
                ymin = min(ymin, float(yd[m].min()))
                ymax = max(ymax, float(yd[m].max()))
        if not (np.isfinite(ymin) and np.isfinite(ymax)):
            return
        if ymax > ymin:
            pad = (ymax - ymin) * 0.05
            ax.set_ylim(ymin - pad, ymax + pad)
        else:  # flat line — give it a small symmetric band so it's visible
            pad = abs(ymin) * 0.05 or 1.0
            ax.set_ylim(ymin - pad, ymax + pad)

    def _ts_set_xlim(self, xlim):
        self._ts_xlim_current = xlim
        for i, (ax, canvas) in enumerate(zip(self._ts_axes, self._ts_canvases)):
            ax.set_xlim(xlim)                       # ax2 shares x via twinx
            self._ts_autoscale_y(ax)
            self._ts_autoscale_y(self._ts_axes2[i])
            self._ts_draw_hist(i)                   # histogram tracks the visible window
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
