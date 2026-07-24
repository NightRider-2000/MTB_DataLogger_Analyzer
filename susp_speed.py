import tkinter as tk
import numpy as np

import widgets as w
from constants import BG, DARK, GRID, HIST_COLORS, HIST_BINS, SUSP_LSHS_BAND_MMPS

_LSHS_COLOR = HIST_COLORS[2]   # green – LS↔HS transition band shading

_COMP_COLOR    = HIST_COLORS[1]   # blue   – compression
_REBOUND_COLOR = HIST_COLORS[0]   # orange – rebound

# Position-vs-speed 2D histograms (right column): adaptive bin count targeting a
# MEAN occupancy of at least this many samples per bin (nbins/axis ≈ sqrt(N/50),
# clipped below) so the color field stays smooth instead of speckled.
_MAP_MIN_PER_BIN = 50
_MAP_BINS_MIN    = 20
_MAP_BINS_MAX    = 100


class SuspSpeedMixin:

    def _build_susp_speed_tab(self):
        outer = tk.Frame(self.susp_speed_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        fig = w.make_figure(figsize=(12, 7), dpi=100)
        # Left column: comp/rebound speed histograms (x linked front↔rear).
        # Right column: position-vs-speed 2D histograms (front top, rear bottom,
        # x linked) — each row is a nested sub-gridspec [map | colorbar] with a
        # tiny wspace so the colorbar hugs its map (the outer wspace only
        # separates the left/right columns). FIXED colorbar axes — a
        # fig.colorbar() per redraw would stack new axes each time.
        gs  = fig.add_gridspec(2, 2, width_ratios=[1, 1.25],
                               hspace=0.4, wspace=0.3)
        sub_top = gs[0, 1].subgridspec(1, 2, width_ratios=[30, 1], wspace=0.04)
        sub_bot = gs[1, 1].subgridspec(1, 2, width_ratios=[30, 1], wspace=0.04)

        self._ax_hist_front = fig.add_subplot(gs[0, 0])
        self._ax_hist_rear  = fig.add_subplot(gs[1, 0], sharex=self._ax_hist_front)
        self._ax_map_front  = fig.add_subplot(sub_top[0, 0])
        # x (position %) LINKED between the two maps so front/rear frame the same
        # travel range and any x change tracks both.
        self._ax_map_rear   = fig.add_subplot(sub_bot[0, 0], sharex=self._ax_map_front)
        self._cax_map_front = fig.add_subplot(sub_top[0, 1])
        self._cax_map_rear  = fig.add_subplot(sub_bot[0, 1])

        for ax in (self._ax_hist_front, self._ax_hist_rear,
                   self._ax_map_front, self._ax_map_rear):
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

        for ax in (self._ax_hist_front, self._ax_hist_rear,
                   self._ax_map_front, self._ax_map_rear):
            ax.clear()
            ax.set_facecolor(BG)
        self._cax_map_front.clear()
        self._cax_map_rear.clear()

        # Keep only rows at the nominal sample interval (within ±50% of the
        # data's own median period — never a hardcoded rate). Drops multi-file
        # concat gaps and any dropped-sample jumps.
        _dt_s  = self.cal_result_df.index.to_series().diff().dt.total_seconds()
        _period = w.sample_period_s(self.cal_result_df.index)
        if _period:
            _mask = _dt_s.between(0.5 * _period, 1.5 * _period)
            df = self.cal_result_df[_mask]
        else:
            df = self.cal_result_df

        # Filter to rows where rear wheel speed > 4.5 mph (bike is moving)
        _rr_spd_col = "Rear_Horz_Wheel_Spd_mph"
        if _rr_spd_col in df.columns:
            df = df[df[_rr_spd_col] > 4.5]

        # SHAFT speeds (derivative of the raw sensor/shaft position) — the
        # quantity damper LS/HS circuits actually see, so the LS↔HS band needs
        # no motion-ratio conversion.
        col_front = "Fork_Shaft_Spd_mmps"
        col_rear  = "Shock_Shaft_Spd_mmps"

        # ── Histograms ────────────────────────────────────────────────────────
        # Shared robust speed range across BOTH ends (the axes are sharex'd) —
        # 95th pct of |speed| (the 2D maps' speed axis stays at 99.5th).
        _spd_maxes = [float(np.percentile(np.abs(df[c].dropna().values), 95.0))
                      for c in (col_front, col_rear)
                      if c in df.columns and df[c].notna().any()]
        _spd_shared_max = max(_spd_maxes) if _spd_maxes else 1.0

        for ax_hist, col, label in [
            (self._ax_hist_front, col_front, "Fork Shaft Speed (mm/s)"),
            (self._ax_hist_rear,  col_rear,  "Shock Shaft Speed (mm/s)"),
        ]:
            if col not in df.columns:
                w.style_ax(ax_hist)
                continue

            series  = df[col].dropna()
            comp    = series[series < 0]
            rebound = series[series > 0]

            comp_abs = comp.abs() if not comp.empty else comp
            # Shared edges so the two overlaid distributions line up bin-for-bin,
            # over the front↔rear SHARED robust range (linked axes).
            bin_max   = _spd_shared_max
            bin_edges = np.linspace(0, bin_max, HIST_BINS + 1)

            if not comp.empty:
                w.plot_hist_line(ax_hist, comp_abs, bin_edges, color=_COMP_COLOR,
                                 label=(f"Compression  n={len(comp)}  "
                                        f"mean={comp_abs.mean():.1f}  max={comp_abs.max():.0f}"))
                ax_hist.axvline(comp_abs.mean(), color=_COMP_COLOR,
                                linestyle="--", linewidth=1.2)
            if not rebound.empty:
                w.plot_hist_line(ax_hist, rebound, bin_edges, color=_REBOUND_COLOR,
                                 label=(f"Rebound  n={len(rebound)}  "
                                        f"mean={rebound.mean():.1f}  max={rebound.max():.0f}"))
                ax_hist.axvline(rebound.mean(), color=_REBOUND_COLOR,
                                linestyle="--", linewidth=1.2)

            ax_hist.axvline(0, color=DARK, linewidth=1.0, linestyle="-")
            # LS↔HS damping transition band (shaft speed — no conversion needed).
            _b0, _b1 = SUSP_LSHS_BAND_MMPS
            ax_hist.axvspan(_b0, _b1, color=_LSHS_COLOR, alpha=0.12,
                            label=f"LS↔HS transition {_b0:.0f}–{_b1:.0f} mm/s")
            ax_hist.set_xlim(0, bin_max)
            handles, _ = ax_hist.get_legend_handles_labels()
            if handles:
                ax_hist.legend(fontsize=10, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
            ax_hist.set_title(f"{label}  (sample based)", color=DARK, fontsize=13)
            ax_hist.set_xlabel("mm/s", color=DARK, fontsize=12)
            ax_hist.set_ylabel("Count", color=DARK, fontsize=12)
            w.style_ax(ax_hist)

        # ── Position-vs-speed 2D histograms (front top, rear bottom) ─────────
        # Common x (position %) range across BOTH ends — the axes are sharex'd,
        # so bin each map over the same span rather than its own.
        _x_ranges = []
        for _pc in ("Fork_Pos_Perc", "Shock_Pos_Perc"):
            if _pc in df.columns:
                _pv = df[_pc].dropna().values
                if len(_pv):
                    _x_ranges.append(np.percentile(_pv, [0.2, 99.8]))
        _x_shared = ((min(r[0] for r in _x_ranges), max(r[1] for r in _x_ranges))
                     if _x_ranges else None)

        for ax, cax, pos_col, spd_col, label in [
            (self._ax_map_front, self._cax_map_front,
             "Fork_Pos_Perc", col_front, "Fork"),
            (self._ax_map_rear, self._cax_map_rear,
             "Shock_Pos_Perc", col_rear, "Shock"),
        ]:
            drawn = False
            if pos_col in df.columns and spd_col in df.columns:
                pair = df[[pos_col, spd_col]].dropna()
                n = len(pair)
                if n > _MAP_MIN_PER_BIN * 4:
                    xv = pair[pos_col].values.astype(float)
                    yv = pair[spd_col].values.astype(float)
                    # Adaptive bin count: nbins/axis ≈ sqrt(N / target-per-bin),
                    # so a typical bin holds ≥ _MAP_MIN_PER_BIN samples and the
                    # color field transitions smoothly instead of speckling.
                    nb = int(np.clip(np.sqrt(n / _MAP_MIN_PER_BIN),
                                     _MAP_BINS_MIN, _MAP_BINS_MAX))
                    # Robust ranges so a few outliers don't stretch the frame;
                    # x uses the SHARED front+rear span (linked axes).
                    x0, x1 = _x_shared
                    y1 = np.percentile(np.abs(yv), 99.5)
                    from matplotlib.colors import LogNorm
                    _, _, _, im = ax.hist2d(
                        xv, yv, bins=nb,
                        range=[[x0, x1], [-y1, y1]],
                        cmap="hot", cmin=1, norm=LogNorm())
                    ax.axhline(0, color=DARK, linewidth=0.8, linestyle="--")
                    # LS↔HS transition band, both directions (comp + rebound)
                    _b0, _b1 = SUSP_LSHS_BAND_MMPS
                    for lo, hi in ((_b0, _b1), (-_b1, -_b0)):
                        ax.axhspan(lo, hi, color=_LSHS_COLOR, alpha=0.15)
                    cb = self._fig_susp_spd.colorbar(im, cax=cax)
                    cb.set_label("Count", color=DARK)
                    cb.ax.tick_params(colors=DARK)
                    for lbl in cb.ax.get_yticklabels():
                        lbl.set_color(DARK)
                    # Comp (negative speed) below the zero line, Rebound above
                    ax.text(0.985, 0.03, "Comp", transform=ax.transAxes,
                            color=DARK, fontsize=11, ha="right", va="bottom",
                            fontweight="bold")
                    ax.text(0.985, 0.97, "Rebound", transform=ax.transAxes,
                            color=DARK, fontsize=11, ha="right", va="top",
                            fontweight="bold")
                    drawn = True
            cax.set_visible(drawn)
            if not drawn:
                ax.text(0.5, 0.5, "No Data Available", transform=ax.transAxes,
                        ha="center", va="center", color=DARK, fontsize=14)
            ax.set_title(f"{label}: Shaft Speed vs Position", color=DARK, fontsize=13)
            ax.set_xlabel(f"{label} Pos (%)", color=DARK, fontsize=12)
            ax.set_ylabel("Shaft Speed (mm/s)", color=DARK, fontsize=12)
            w.style_ax(ax)
            ax.grid(False)   # gridlines on top of a dense colormap just add noise

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fig_susp_spd.tight_layout()
        self._canvas_susp_spd.draw()
