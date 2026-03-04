import tkinter as tk
import numpy as np

import widgets as w
from constants import BG, DARK, GRID

_COMP_COLOR    = "#2a7be0"   # blue   – compression
_REBOUND_COLOR = "#e05c2a"   # orange – rebound
_SCATTER_COLOR = "#2ab55c"   # green  – scatter dots


class SuspSpeedMixin:

    def _build_susp_speed_tab(self):
        outer = tk.Frame(self.susp_speed_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        fig = w.make_figure(figsize=(12, 7), dpi=100)
        gs  = fig.add_gridspec(2, 2, width_ratios=[1, 1.2], hspace=0.4, wspace=0.35)

        self._ax_hist_front  = fig.add_subplot(gs[0, 0])
        self._ax_hist_rear   = fig.add_subplot(gs[1, 0])
        self._ax_scatter_spd = fig.add_subplot(gs[:, 1])

        for ax in (self._ax_hist_front, self._ax_hist_rear, self._ax_scatter_spd):
            ax.set_facecolor(BG)

        canvas, cv_widget = w.make_canvas(fig, outer)
        cv_widget.pack(fill=tk.BOTH, expand=True)
        self._fig_susp_spd    = fig
        self._canvas_susp_spd = canvas

    def _update_susp_speed_plots(self):
        if not hasattr(self, "_ax_hist_front"):
            return
        if self.cal_result_df is None:
            return

        for ax in (self._ax_hist_front, self._ax_hist_rear, self._ax_scatter_spd):
            ax.clear()
            ax.set_facecolor(BG)

        col_front = "Front_Wheel_Spd_mmPs"
        col_rear  = "Rear_Wheel_Spd_mmPs"

        # ── Histograms ────────────────────────────────────────────────────────
        for ax_hist, col, label in [
            (self._ax_hist_front, col_front, "Front Susp Speed (mm/s)"),
            (self._ax_hist_rear,  col_rear,  "Rear Susp Speed (mm/s)"),
        ]:
            if col not in self.cal_result_df.columns:
                w.style_ax(ax_hist)
                continue

            series  = self.cal_result_df[col].dropna()
            comp    = series[series < 0]
            rebound = series[series > 0]

            comp_abs  = comp.abs() if not comp.empty else comp
            maxvals   = [s.max() for s in (comp_abs, rebound) if not s.empty]
            bin_max   = max(maxvals) if maxvals else 1.0
            bin_edges = np.linspace(0, bin_max, 201)

            if not comp.empty:
                ax_hist.hist(comp_abs, bins=bin_edges, alpha=0.40, color=_COMP_COLOR,
                             label=f"Compression  n={len(comp)}  mean={comp_abs.mean():.1f}")
                ax_hist.axvline(comp_abs.mean(), color=_COMP_COLOR,
                                linestyle="--", linewidth=1.2)
            if not rebound.empty:
                ax_hist.hist(rebound, bins=bin_edges, alpha=0.40, color=_REBOUND_COLOR,
                             label=f"Rebound  n={len(rebound)}  mean={rebound.mean():.1f}")
                ax_hist.axvline(rebound.mean(), color=_REBOUND_COLOR,
                                linestyle="--", linewidth=1.2)

            ax_hist.axvline(0, color=DARK, linewidth=1.0, linestyle="-")
            ax_hist.set_xlim(0, 1200)
            ax_hist.legend(fontsize=7, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
            ax_hist.set_title(label, color=DARK, fontsize=9)
            ax_hist.set_xlabel("mm/s", color=DARK, fontsize=8)
            ax_hist.set_ylabel("Count", color=DARK, fontsize=8)
            w.style_ax(ax_hist)

        # ── Scatter: front speed (x) vs rear speed (y) ────────────────────────
        ax = self._ax_scatter_spd
        if (col_front in self.cal_result_df.columns
                and col_rear in self.cal_result_df.columns):
            pair = self.cal_result_df[[col_front, col_rear]].dropna()
            x = pair[col_front].values
            y = pair[col_rear].values

            if len(x) > 1:
                ax.scatter(x, y, s=1, alpha=0.25, color=_SCATTER_COLOR)

                lim = 2000
                ax.set_xlim(-lim, lim)
                ax.set_ylim(-lim, lim)

                # Zero lines
                ax.axhline(0, color=DARK, linewidth=0.6, linestyle="--")
                ax.axvline(0, color=DARK, linewidth=0.6, linestyle="--")

                # 1:1 line
                ax.plot([-lim, lim], [-lim, lim],
                        color="black", linewidth=1.2, label="1:1")

                # Trend line forced through origin
                slope = np.dot(x, y) / np.dot(x, x)
                ax.plot([-lim, lim], [-lim * slope, lim * slope],
                        color=_REBOUND_COLOR, linewidth=1.5, linestyle="--",
                        label=f"trend  slope={slope:.2f}")

                # Quadrant labels
                ax.text(0.76, 0.93, "Comp", transform=ax.transAxes,
                        color=DARK, fontsize=9, ha="center", va="top",
                        fontweight="bold")
                ax.text(0.24, 0.07, "Rebound", transform=ax.transAxes,
                        color=DARK, fontsize=9, ha="center", va="bottom",
                        fontweight="bold")

                ax.legend(fontsize=7, facecolor=BG, edgecolor=DARK, labelcolor=DARK)

        ax.set_title("Front vs Rear Suspension Speed", color=DARK, fontsize=9)
        ax.set_xlabel("Front Speed (mm/s)", color=DARK, fontsize=8)
        ax.set_ylabel("Rear Speed (mm/s)", color=DARK, fontsize=8)
        w.style_ax(ax)

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fig_susp_spd.tight_layout()
        self._canvas_susp_spd.draw()
