import tkinter as tk
import numpy as np

import widgets as w
from constants import (BG, DARK, GRID, HIST_COLORS,
                       SCATTER_ORIG_COLOR, TREND_ORIG_COLOR)

_COMP_COLOR    = HIST_COLORS[1]   # blue   – compression
_REBOUND_COLOR = HIST_COLORS[0]   # orange – rebound
_SCATTER_COLOR = HIST_COLORS[2]   # green  – scatter dots


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

        # Filter to valid sample intervals only (10–20 ms), screen-local
        _dt_s  = self.cal_result_df.index.to_series().diff().dt.total_seconds()
        _dt_ms = _dt_s * 1000
        _mask  = _dt_ms.between(10, 20)
        df = self.cal_result_df[_mask]

        # Filter to rows where rear wheel speed > 4.5 mph (bike is moving)
        _rr_spd_col = "Rear_Horz_Wheel_Spd_mph"
        if _rr_spd_col in df.columns:
            df = df[df[_rr_spd_col] > 4.5]

        col_front = "Front_Vert_Wheel_Spd_mmPs"
        col_rear  = "Rear_Vert_Wheel_Spd_mmPs"

        # ── Histograms ────────────────────────────────────────────────────────
        for ax_hist, col, label in [
            (self._ax_hist_front, col_front, "Front Susp Speed (mm/s)"),
            (self._ax_hist_rear,  col_rear,  "Rear Susp Speed (mm/s)"),
        ]:
            if col not in df.columns:
                w.style_ax(ax_hist)
                continue

            series  = df[col].dropna()
            comp    = series[series < 0]
            rebound = series[series > 0]

            comp_abs  = comp.abs() if not comp.empty else comp
            maxvals   = [s.max() for s in (comp_abs, rebound) if not s.empty]
            bin_max   = max(maxvals) if maxvals else 1.0
            bin_edges = np.linspace(0, bin_max, 201)

            if not comp.empty:
                ax_hist.hist(comp_abs, bins=bin_edges, alpha=0.45, color=_COMP_COLOR,
                             label=f"Compression  n={len(comp)}  mean={comp_abs.mean():.1f}")
                ax_hist.axvline(comp_abs.mean(), color=_COMP_COLOR,
                                linestyle="--", linewidth=1.2)
            if not rebound.empty:
                ax_hist.hist(rebound, bins=bin_edges, alpha=0.45, color=_REBOUND_COLOR,
                             label=f"Rebound  n={len(rebound)}  mean={rebound.mean():.1f}")
                ax_hist.axvline(rebound.mean(), color=_REBOUND_COLOR,
                                linestyle="--", linewidth=1.2)

            ax_hist.axvline(0, color=DARK, linewidth=1.0, linestyle="-")
            ax_hist.set_xlim(0, 1200)
            handles, _ = ax_hist.get_legend_handles_labels()
            if handles:
                ax_hist.legend(fontsize=7, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
            ax_hist.set_title(label, color=DARK, fontsize=9)
            ax_hist.set_xlabel("mm/s", color=DARK, fontsize=8)
            ax_hist.set_ylabel("Count", color=DARK, fontsize=8)
            w.style_ax(ax_hist)

        # ── Scatter: original + time-aligned rear speed vs front speed ──────────
        ax = self._ax_scatter_spd
        x_orig = np.array([])
        y_orig = np.array([])
        x_aln  = np.array([])
        y_aln  = np.array([])
        if (col_front in df.columns
                and col_rear in df.columns):
            front_series = df[col_front].dropna()
            rear_series  = df[col_rear].dropna()

            if len(front_series) > 1 and len(rear_series) > 1:
                # Original (unaligned) pairs
                pair   = df[[col_front, col_rear]].dropna()
                x_orig = pair[col_front].values
                y_orig = pair[col_rear].values

                # Numeric timestamps (seconds) for interpolation
                t_front = front_series.index.view(np.int64) / 1e9
                t_rear  = rear_series.index.view(np.int64)  / 1e9
                x_all   = front_series.values

                # Dynamic lag: wheelbase_mm / rear_speed_mm_per_s
                _wb_mm      = float(getattr(self, "wheel_base_var",
                                            type("", (), {"get": lambda s: "1242"})()).get())
                _MPH_TO_MMS = 1609.344 / 3600.0 * 1000.0   # mph → mm/s
                _rr_spd_col = "Rear_Horz_Wheel_Spd_mph"
                if _rr_spd_col in df.columns:
                    rr_spd = df[_rr_spd_col].dropna()
                    rr_t   = rr_spd.index.view(np.int64) / 1e9
                    rr_mph = np.interp(t_front, rr_t, rr_spd.values)
                    lag_s  = _wb_mm / (np.maximum(rr_mph, 3.0) * _MPH_TO_MMS)
                else:
                    lag_s = np.zeros(len(t_front))

                # Look up rear susp speed at t_front + lag (same road feature)
                t_target = t_front + lag_s
                y_all    = np.interp(t_target, t_rear, rear_series.values)

                # Drop samples where target time is outside the rear signal range
                valid = (t_target >= t_rear[0]) & (t_target <= t_rear[-1])
                x_aln = x_all[valid]
                y_aln = y_all[valid]

        def _plot_trend_and_bins(ax, x, y, scatter_color, trend_color, bin_color,
                                 scatter_label, trend_label_prefix, bin_label_prefix):
            ax.scatter(x, y, s=1, alpha=0.15, color=scatter_color, label=scatter_label)
            slope = np.dot(x, y) / np.dot(x, x)
            ax.plot([-lim, lim], [-lim * slope, lim * slope],
                    color=trend_color, linewidth=1.5, linestyle="--",
                    label=f"{trend_label_prefix}  slope={slope:.2f}")
            if len(x) > 20:
                bins = np.linspace(x.min(), x.max(), 21)
                bin_centers, bin_means, bin_stds = [], [], []
                for lo, hi in zip(bins[:-1], bins[1:]):
                    mask = (x >= lo) & (x < hi)
                    if mask.sum() > 0:
                        bin_centers.append((lo + hi) / 2)
                        bin_means.append(y[mask].mean())
                        bin_stds.append(y[mask].std())
                if bin_centers:
                    bc = np.array(bin_centers)
                    bm = np.array(bin_means)
                    bs = np.array(bin_stds)
                    ax.plot(bc, bm, color=bin_color, linewidth=2.0,
                            marker="o", markersize=4, label=f"{bin_label_prefix} bin mean", zorder=6)
                    ax.fill_between(bc, bm - bs, bm + bs,
                                    alpha=0.20, color=bin_color, label=f"{bin_label_prefix} ±1σ")

        lim = 2000
        if len(x_orig) > 1 or len(x_aln) > 1:
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim, lim)

            # Zero lines
            ax.axhline(0, color=DARK, linewidth=0.6, linestyle="--")
            ax.axvline(0, color=DARK, linewidth=0.6, linestyle="--")

            # 1:1 line
            ax.plot([-lim, lim], [-lim, lim],
                    color="black", linewidth=1.2, label="1:1")

            if len(x_orig) > 1:
                _plot_trend_and_bins(ax, x_orig, y_orig,
                                     scatter_color=SCATTER_ORIG_COLOR,
                                     trend_color=TREND_ORIG_COLOR,
                                     bin_color=TREND_ORIG_COLOR,
                                     scatter_label="Original",
                                     trend_label_prefix="Orig trend",
                                     bin_label_prefix="Orig")
            if len(x_aln) > 1:
                _plot_trend_and_bins(ax, x_aln, y_aln,
                                     scatter_color=_SCATTER_COLOR,
                                     trend_color=_REBOUND_COLOR,
                                     bin_color=DARK,
                                     scatter_label="Aligned",
                                     trend_label_prefix="Aligned trend",
                                     bin_label_prefix="Aligned")

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
