import tkinter as tk
import warnings

import widgets as w
from constants import BG, DARK, GRID, HIST_BAR_COLOR, HIST_BINS


class SagMixin:

    def _build_sag_tab(self):
        frame = tk.Frame(self.sag_tab, bg=BG)
        frame.pack(fill=tk.BOTH, expand=True)

        self.fig_sag = w.make_figure(figsize=(14, 6), dpi=100)
        # 2×3: the mm-displacement column was removed (not useful — the % and
        # wheel-position columns carry the sag story). Cols: Pos%, Wheel Pos%,
        # Wheel Pos% (≥98th pctile zoom).
        self.axes_sag = self.fig_sag.subplots(2, 3)

        for ax in self.axes_sag.flat:
            ax.set_facecolor(BG)

        # Row labels
        self.fig_sag.text(0.01, 0.73, "Front Suspension",
                          rotation=90, va="center", ha="center",
                          color=DARK, fontsize=15, fontweight="bold")
        self.fig_sag.text(0.01, 0.27, "Rear Suspension",
                          rotation=90, va="center", ha="center",
                          color=DARK, fontsize=15, fontweight="bold")

        self.canvas_sag, cv_widget = w.make_canvas(self.fig_sag, frame)
        cv_widget.pack(fill=tk.BOTH, expand=True)
        self.canvas_sag.draw()

    def _update_sag_plots(self):
        if not hasattr(self, "axes_sag") or self.cal_result_df is None:
            return

        for ax in self.axes_sag.flat:
            ax.clear()
            ax.set_facecolor(BG)

        # Row 0 — Front Suspension
        _sag_plot(self.axes_sag[0][0], self.cal_result_df, "Fork_Pos_Perc")
        _sag_plot(self.axes_sag[0][1], self.cal_result_df, "Front_Wheel_Pos_Perc")
        _sag_plot(self.axes_sag[0][2], self.cal_result_df, "Front_Wheel_Pos_Perc", zoom_p90=True)

        # Row 1 — Rear Suspension
        _sag_plot(self.axes_sag[1][0], self.cal_result_df, "Shock_Pos_Perc")
        _sag_plot(self.axes_sag[1][1], self.cal_result_df, "Rear_Wheel_Pos_Perc")
        _sag_plot(self.axes_sag[1][2], self.cal_result_df, "Rear_Wheel_Pos_Perc", zoom_p90=True)

        for ax in self.axes_sag.flat:
            w.style_ax(ax)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig_sag.tight_layout(rect=[0.03, 0, 1, 1])
        self.canvas_sag.draw()


def _sag_plot(ax, df, col, zoom_p90=False):
    if col not in df.columns:
        ax.set_title(col, color=DARK, fontsize=12)
        return
    data = df[col].dropna()
    if data.empty:
        ax.set_title(col, color=DARK, fontsize=12)
        return
    import numpy as np
    color = HIST_BAR_COLOR
    mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
    counts, bin_edges = w.plot_hist_line(ax, data, HIST_BINS, color=color)
    ax.axvline(mean, color=color, linestyle="--", linewidth=1.5)
    ax.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
    ax.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
    ax.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
    ax.axvspan(mean - std, mean + std, alpha=0.12, color=color)
    ax.text(0.97, 0.97,
            f"{col}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}",
            transform=ax.transAxes, fontsize=10,
            verticalalignment="top", horizontalalignment="right", color=DARK,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9))
    if zoom_p90:
        x_left = data.quantile(0.98)
        ax.set_xlim(left=x_left)
        visible = counts[bin_edges[1:] >= x_left]
        if visible.size:
            ax.set_ylim(0, visible.max() * 1.15)
        title = f"{col} (≥98th pctile)"
    else:
        title = col
    ax.set_title(title, color=DARK, fontsize=12)
    ax.set_xlabel("Value", color=DARK, fontsize=10)
    ax.set_ylabel("Count", color=DARK, fontsize=10)


