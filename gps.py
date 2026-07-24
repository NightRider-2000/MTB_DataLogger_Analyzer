import tkinter as tk
import warnings
from tkinter import ttk

import numpy as np
import pandas as pd

import basemap
import widgets as w
from constants import (BG, DARK, GRID, GPS_CMAP, GPS_START_COLOR,
                       GPS_FINISH_COLOR, GPS_TOPO_COLOR)

# Preferred default color signal (first one present wins)
_DEFAULT_COLOR_PRIORITY = ["Rear_Horz_Wheel_Spd_mph", "Front_Horz_Wheel_Spd_mph",
                           "gps_spd_mph", "Crank_Spd_RPM"]
# Synthetic "color by" option — elapsed ride time, not a real dataframe column.
_TIME_COLOR_KEY = "Time (s)"
_STRIP_BINS = 1200          # horizontal resolution of the colored time bar
_PICK_FRAC  = 0.015         # marker grab tolerance (fraction of the full range)


class GpsMixin:
    """GPS tab: a colored time-range bar with two draggable markers (green =
    start, red = finish) above a map of the GPS route. Route circles are colored
    by a selectable signal; the same scale colors the time bar. The two markers'
    geographic locations are shown on the map as one large green and one large
    red circle. 'Apply Filter' restricts every analysis tab to the selected
    window; 'Clear Filter' restores."""

    # ── Build ────────────────────────────────────────────────────────────────
    def _build_gps_tab(self):
        outer = tk.Frame(self.gps_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        # Control bar
        ctrl = tk.Frame(outer, bg=BG)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(ctrl, text="Color by:", bg=BG, fg=DARK).pack(side=tk.LEFT, padx=(0, 4))
        self._gps_color_var = tk.StringVar()
        self._gps_color_combo = ttk.Combobox(ctrl, textvariable=self._gps_color_var,
                                              state="readonly", width=26)
        self._gps_color_combo.pack(side=tk.LEFT, padx=(0, 12))
        self._gps_color_combo.bind("<<ComboboxSelected>>", lambda e: self._update_gps_plots())
        self._gps_topo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Topo lines", variable=self._gps_topo_var,
                        command=self._update_gps_plots).pack(side=tk.LEFT, padx=(0, 12))
        w.make_btn(ctrl, "Apply Filter", self._gps_apply_filter).pack(side=tk.LEFT, padx=4)
        w.make_btn(ctrl, "Clear Filter", self._gps_clear_filter).pack(side=tk.LEFT, padx=4)
        w.make_btn(ctrl, "Reset View",   self._gps_reset_view).pack(side=tk.LEFT, padx=4)
        tk.Label(ctrl, text="(scroll = zoom · drag = pan)", bg=BG, fg=GRID,
                 font=("TkDefaultFont", 12)).pack(side=tk.LEFT, padx=(2, 0))
        self._gps_window_label = tk.Label(ctrl, text="", bg=BG, fg=DARK,
                                          font=("TkFixedFont", 13))
        self._gps_window_label.pack(side=tk.LEFT, padx=12)

        # Figure: time bar (top) + map (bottom-left, fills the width) + colorbar (right)
        fig = w.make_figure(figsize=(14, 7.5), dpi=100)
        gs = fig.add_gridspec(2, 2, height_ratios=[1, 16], width_ratios=[70, 1],
                              hspace=0.30, wspace=0.02)
        fig.subplots_adjust(left=0.015, right=0.93, top=0.95, bottom=0.04)
        self._gps_ax_bar = fig.add_subplot(gs[0, 0])
        self._gps_ax_map = fig.add_subplot(gs[1, 0])
        self._gps_ax_cax = fig.add_subplot(gs[1, 1])
        for ax in (self._gps_ax_bar, self._gps_ax_map):
            ax.set_facecolor(BG)

        canvas, cv_widget = w.make_canvas(fig, outer)
        cv_widget.pack(fill=tk.BOTH, expand=True)
        self._gps_fig    = fig
        self._gps_canvas = canvas
        self._gps_resize_job = None

        # Interaction state
        self._gps_t0          = None          # base start timestamp
        self._gps_total_s     = 0.0           # base duration (s)
        self._gps_marker_secs = [0.0, 0.0]    # [lo, hi] marker positions (s from start)
        self._gps_mk_lines    = []            # the two marker Line2D handles
        self._gps_endpoints   = None          # start/finish circles (PathCollection)
        self._gps_drag        = None          # index of marker being dragged, or None
        self._gps_basemap     = None          # cached (img, mercator_extent)
        self._gps_elev        = None          # cached (elevation_grid, mercator_extent)
        self._gps_bbox_key    = None          # bbox the cached basemap was fetched for
        self._gps_use_merc    = False         # True when a satellite basemap is shown
        self._gps_view        = None          # user pan/zoom mercator (xlim, ylim) or None
        self._gps_pan         = None          # active pan gesture state
        self._gps_nav_job     = None          # debounced tile-refetch after pan/zoom

        canvas.mpl_connect("button_press_event",   self._gps_on_press)
        canvas.mpl_connect("motion_notify_event",  self._gps_on_motion)
        canvas.mpl_connect("button_release_event", self._gps_on_release)
        canvas.mpl_connect("scroll_event",         self._gps_on_scroll)
        canvas.mpl_connect("resize_event",         self._gps_on_resize)

    def _gps_on_resize(self, event):
        """Re-fill the map to the new window width (debounced)."""
        if self._gps_resize_job is not None:
            try:
                self.after_cancel(self._gps_resize_job)
            except Exception:
                pass
        self._gps_resize_job = self.after(200, self._update_gps_plots)

    # ── Data helpers ─────────────────────────────────────────────────────────
    def _gps_base(self):
        """Full (unfiltered) calibrated frame, or None if unavailable."""
        return getattr(self, "_cal_full", None)

    @staticmethod
    def _gps_has_fix(df):
        return (df is not None and "gps_lat" in df.columns and "gps_lon" in df.columns
                and df["gps_lat"].notna().any() and df["gps_lon"].notna().any())

    def _gps_color_columns(self, base):
        cols = [c for c in base.columns if pd.api.types.is_numeric_dtype(base[c])]
        return [_TIME_COLOR_KEY] + sorted(cols)

    def _gps_color_values(self, df, color_col):
        """Resolve color_col to a Series aligned to df's index. _TIME_COLOR_KEY
        is synthetic (elapsed seconds since the ride start), not a real column."""
        if color_col == _TIME_COLOR_KEY:
            return pd.Series(self._gps_secs(df.index), index=df.index)
        if color_col in df.columns:
            return df[color_col].ffill()
        return pd.Series(np.zeros(len(df.index)), index=df.index)

    def _gps_secs(self, index):
        return (index - self._gps_t0).total_seconds().values

    def _gps_reset_markers(self):
        """Reset the time window to the full record (called on fresh data load)."""
        base = self._gps_base()
        if base is None or len(base.index) == 0:
            self._gps_t0, self._gps_total_s, self._gps_marker_secs = None, 0.0, [0.0, 0.0]
            return
        self._gps_t0      = base.index[0]
        self._gps_total_s = float((base.index[-1] - self._gps_t0).total_seconds())
        self._gps_marker_secs = [0.0, self._gps_total_s]
        self._gps_view = None          # new ride → refit the map to its route

    # ── Draw ─────────────────────────────────────────────────────────────────
    def _update_gps_plots(self):
        if not hasattr(self, "_gps_ax_map"):
            return
        base = self._gps_base()
        self._gps_ax_bar.clear(); self._gps_ax_bar.set_facecolor(BG)
        self._gps_ax_map.clear(); self._gps_ax_map.set_facecolor(BG)
        self._gps_ax_cax.clear()
        self._gps_endpoints = None

        if not self._gps_has_fix(base):
            self._gps_ax_map.text(0.5, 0.5, "No GPS fix in the loaded data",
                                  transform=self._gps_ax_map.transAxes, ha="center",
                                  va="center", color=DARK, fontsize=15)
            for ax in (self._gps_ax_bar, self._gps_ax_map):
                w.style_ax(ax)
            self._gps_ax_cax.axis("off")
            self._gps_canvas.draw_idle()
            return

        if self._gps_t0 is None:
            self._gps_reset_markers()

        # Resolve color signal + populate the combobox
        cols = self._gps_color_columns(base)
        self._gps_color_combo["values"] = cols
        color_col = self._gps_color_var.get()
        if color_col not in cols:
            color_col = next((c for c in _DEFAULT_COLOR_PRIORITY if c in cols),
                             cols[0] if cols else "")
            self._gps_color_var.set(color_col)

        color_full = self._gps_color_values(base, color_col)
        # Scale the color range to the 2nd–98th percentile so a few outlier
        # samples (e.g. GPS speed spikes) don't compress the whole colormap.
        if color_full.notna().any():
            vmin, vmax = (float(v) for v in
                          np.nanpercentile(color_full.values, [2, 98]))
        else:
            vmin, vmax = 0.0, 1.0
        if vmin == vmax:
            vmax = vmin + 1.0

        self._draw_time_bar(base, color_full, vmin, vmax)
        sc = self._draw_map(base, color_col, vmin, vmax)
        self._draw_colorbar(sc, color_col)
        self._draw_endpoints(base)
        self._update_window_label()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._gps_canvas.draw_idle()

    def _draw_time_bar(self, base, color_full, vmin, vmax):
        from scipy.stats import binned_statistic
        ax = self._gps_ax_bar
        secs = self._gps_secs(base.index)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            strip, _, _ = binned_statistic(secs, color_full.values,
                                           statistic=np.nanmean, bins=_STRIP_BINS,
                                           range=(0, self._gps_total_s))
        cmap = self._gps_cmap()
        ax.imshow(strip[None, :], extent=[0, self._gps_total_s, 0, 1], aspect="auto",
                  origin="lower", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
        ax.set_xlim(0, self._gps_total_s)
        ax.set_yticks([])
        ax.set_title("Ride timeline — drag the green (start) / red (finish) markers",
                     color=DARK, fontsize=13)
        ax.xaxis.set_major_formatter(self._gps_time_formatter())
        for s in ax.spines.values():
            s.set_edgecolor(DARK)
        ax.tick_params(colors=DARK)

        # Draggable markers — drawn past the strip top & bottom so they read as
        # grab handles (ymin/ymax in axes fraction, clip_on off to spill over).
        self._gps_mk_lines = []
        for mx in self._gps_marker_secs:
            ln = ax.axvline(mx, lw=15, ymin=-0.9, ymax=1.9, solid_capstyle="butt")
            ln.set_clip_on(False)
            self._gps_mk_lines.append(ln)
        self._gps_color_markers()

    def _draw_map(self, base, color_col, vmin, vmax):
        ax = self._gps_ax_map

        # Satellite basemap covers the FULL route extent (cached; survives filters).
        self._gps_ensure_basemap(base)

        active = self.cal_result_df          # filtered view (or full)
        m = active["gps_lat"].notna() & active["gps_lon"].notna()
        lat = active.loc[m, "gps_lat"].values
        lon = active.loc[m, "gps_lon"].values
        cvals = self._gps_color_values(active, color_col).loc[m].values
        x, y = self._gps_project(lon, lat)

        ax.set_title("GPS Route", color=DARK, fontsize=13)
        if self._gps_use_merc:
            img, extent = self._gps_basemap
            ax.imshow(img, extent=extent, origin="upper", zorder=0, interpolation="bilinear")
            if self._gps_topo_var.get():
                self._draw_topo_contours(ax)
            (xlim, ylim) = self._gps_merc_limits
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.set_aspect("equal", adjustable="datalim")
            ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
            for s in ax.spines.values():
                s.set_edgecolor(DARK)
            ax.text(0.99, 0.01, basemap.ATTRIBUTION, transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=8, color="#eeeeee",
                    zorder=5)
        else:
            if len(lat):
                ax.set_aspect(1.0 / max(np.cos(np.radians(float(np.nanmean(lat)))), 1e-3))
            ax.set_xlabel("Longitude (°)", color=DARK, fontsize=12)
            ax.set_ylabel("Latitude (°)", color=DARK, fontsize=12)
            ax.ticklabel_format(useOffset=False, style="plain")
            w.style_ax(ax)

        sc = ax.scatter(x, y, c=cvals, cmap=self._gps_cmap(), vmin=vmin, vmax=vmax,
                        s=14, linewidths=0, zorder=2)
        return sc

    def _gps_axes_aspect(self):
        """Width/height ratio of the map axes box (so the basemap can fill it)."""
        try:
            pos = self._gps_ax_map.get_position()
            fw, fh = self._gps_fig.get_size_inches()
            a = (pos.width * fw) / (pos.height * fh)
            return a if a > 0.2 else 1.0
        except Exception:
            return 1.7

    def _gps_ensure_basemap(self, base):
        """Frame the map (route-fit, or the user's pan/zoom view) to the map-axes
        aspect so the satellite fills the panel undistorted, then fetch+cache the
        basemap/DEM for that extent at a zoom suited to its size. Sets
        self._gps_use_merc + self._gps_merc_limits; falls back to lat/lon offline."""
        m = base["gps_lat"].notna() & base["gps_lon"].notna()
        lat = base.loc[m, "gps_lat"].values
        lon = base.loc[m, "gps_lon"].values
        if len(lat) == 0:
            self._gps_use_merc = False
            return

        aspect = self._gps_axes_aspect()
        if self._gps_view is not None:
            # User has panned/zoomed — keep their center + vertical span, fill width.
            (xl, xr), (yb, yt) = self._gps_view
            cx, cy = (xl + xr) / 2.0, (yb + yt) / 2.0
            hy = max((yt - yb) / 2.0, 30.0)
            hx = hy * aspect
        else:
            # Auto route-fit: expand the route bbox to the axes aspect.
            mx, my = basemap.lonlat_to_mercator(lon, lat)
            cx, cy = (mx.min() + mx.max()) / 2.0, (my.min() + my.max()) / 2.0
            hx = max((mx.max() - mx.min()) / 2.0 * 1.10, 60.0)
            hy = max((my.max() - my.min()) / 2.0 * 1.10, 60.0)
            if hx / hy < aspect:
                hx = hy * aspect
            else:
                hy = hx / aspect
        self._gps_merc_limits = ((cx - hx, cx + hx), (cy - hy, cy + hy))

        lons, lats = basemap.mercator_to_lonlat(
            np.array([cx - hx, cx + hx]), np.array([cy - hy, cy + hy]))
        key = (round(lats.min(), 4), round(lats.max(), 4),
               round(lons.min(), 4), round(lons.max(), 4))
        if key != self._gps_bbox_key:
            self._gps_bbox_key = key
            self._gps_basemap = basemap.fetch_satellite_basemap(*key)
            self._gps_elev = basemap.fetch_elevation_grid(*key)
        self._gps_use_merc = self._gps_basemap is not None

    def _gps_project(self, lon, lat):
        """Project lon/lat to the active map coordinate system (Mercator when a
        satellite basemap is shown, otherwise raw lon/lat)."""
        if self._gps_use_merc:
            return basemap.lonlat_to_mercator(lon, lat)
        return np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)

    def _draw_topo_contours(self, ax):
        """Overlay topographic contour lines (decoded DEM) on the satellite map."""
        if self._gps_elev is None:
            return
        elev, (left, right, bottom, top) = self._gps_elev
        h, wd = elev.shape
        step = max(1, max(h, wd) // 500)          # downsample for contour speed
        z = elev[::step, ::step][::-1]            # flip so row 0 = bottom (increasing y)
        ys = np.linspace(bottom, top, z.shape[0])
        xs = np.linspace(left, right, z.shape[1])
        emin, emax = float(np.nanmin(z)), float(np.nanmax(z))
        rng = emax - emin
        if rng < 1.0:
            return
        interval = 10 if rng <= 60 else 20 if rng <= 150 else 50 if rng <= 400 else 100
        levels = np.arange(np.floor(emin / interval) * interval, emax + interval, interval)
        try:
            cs = ax.contour(xs, ys, z, levels=levels, colors=[GPS_TOPO_COLOR],
                            linewidths=0.6, alpha=0.6, zorder=1)
            if len(cs.levels) > 1:
                ax.clabel(cs, cs.levels[::2], fmt="%d", fontsize=8, colors=GPS_TOPO_COLOR)
        except Exception:
            pass

    def _draw_colorbar(self, sc, color_col):
        cax = self._gps_ax_cax
        cax.clear()
        cb = self._gps_fig.colorbar(sc, cax=cax)
        cb.set_label(color_col, color=DARK, fontsize=12)
        cax.tick_params(colors=DARK, labelsize=7)
        for lbl in cax.get_yticklabels():
            lbl.set_color(DARK)

    def _draw_endpoints(self, base):
        """Two large circles on the map — green at the start marker's location,
        red at the finish marker's — found as the base route points nearest the
        two marker times."""
        ax = self._gps_ax_map
        m = base["gps_lat"].notna() & base["gps_lon"].notna()
        x, y = self._gps_project(base.loc[m, "gps_lon"].values, base.loc[m, "gps_lat"].values)
        self._gps_route_xy = np.column_stack([x, y])
        self._gps_route_secs = self._gps_secs(base.index[m])
        xs, ys = self._endpoint_coords()
        self._gps_endpoints = ax.scatter(
            xs, ys, c=[GPS_START_COLOR, GPS_FINISH_COLOR], s=200,
            edgecolors="white", linewidths=2.0, zorder=6)

    def _endpoint_coords(self):
        """(xs, ys) of the route points nearest the start (min) and finish (max)
        marker times, in the active map coordinate system."""
        if not len(getattr(self, "_gps_route_secs", [])):
            return [], []
        lo, hi = sorted(self._gps_marker_secs)
        si = int(np.argmin(np.abs(self._gps_route_secs - lo)))
        fi = int(np.argmin(np.abs(self._gps_route_secs - hi)))
        return ([self._gps_route_xy[si, 0], self._gps_route_xy[fi, 0]],
                [self._gps_route_xy[si, 1], self._gps_route_xy[fi, 1]])

    def _gps_color_markers(self):
        """Earlier marker → green (start), later marker → red (finish)."""
        if len(self._gps_mk_lines) < 2:
            return
        lo_i = 0 if self._gps_marker_secs[0] <= self._gps_marker_secs[1] else 1
        self._gps_mk_lines[lo_i].set_color(GPS_START_COLOR)
        self._gps_mk_lines[1 - lo_i].set_color(GPS_FINISH_COLOR)

    # ── Interaction: timeline markers + map pan/zoom ─────────────────────────
    def _gps_on_press(self, event):
        # Timeline-bar marker grab
        if event.inaxes is self._gps_ax_bar and event.xdata is not None and self._gps_total_s > 0:
            tol = _PICK_FRAC * self._gps_total_s
            dists = [abs(event.xdata - mx) for mx in self._gps_marker_secs]
            i = int(np.argmin(dists))
            if dists[i] <= max(tol, self._gps_total_s * 0.0):
                self._gps_drag = i
            return
        # Map pan grab (left button) — record pixel anchor + limits at press
        if (event.inaxes is self._gps_ax_map and event.button == 1
                and self._gps_use_merc and event.x is not None):
            self._gps_pan = (event.x, event.y,
                             self._gps_ax_map.get_xlim(), self._gps_ax_map.get_ylim())

    def _gps_on_motion(self, event):
        if self._gps_drag is not None:
            if event.inaxes is not self._gps_ax_bar or event.xdata is None:
                return
            x = float(np.clip(event.xdata, 0.0, self._gps_total_s))
            self._gps_marker_secs[self._gps_drag] = x
            self._gps_mk_lines[self._gps_drag].set_xdata([x, x])
            self._gps_color_markers()
            self._update_endpoints()
            self._update_window_label()
            self._gps_canvas.draw_idle()
            return
        if self._gps_pan is not None and event.x is not None:
            self._gps_do_pan(event)

    def _gps_on_release(self, event):
        self._gps_drag = None
        if self._gps_pan is not None:
            self._gps_pan = None
            self._gps_schedule_nav()      # refetch sharp tiles for the new view

    def _gps_do_pan(self, event):
        """Translate the map so the grabbed point stays under the cursor (uses the
        pixel-to-data scale captured at press, so the view doesn't feed back)."""
        x0, y0, (xl, xr), (yb, yt) = self._gps_pan
        box = self._gps_ax_map.get_window_extent()
        ddx = (event.x - x0) * (xr - xl) / box.width
        ddy = (event.y - y0) * (yt - yb) / box.height
        self._gps_ax_map.set_xlim(xl - ddx, xr - ddx)
        self._gps_ax_map.set_ylim(yb - ddy, yt - ddy)
        self._gps_canvas.draw_idle()

    def _gps_on_scroll(self, event):
        """Scroll-wheel zoom centered on the cursor (Google-Maps style)."""
        if event.inaxes is not self._gps_ax_map or not self._gps_use_merc:
            return
        if event.xdata is None or event.ydata is None:
            return
        scale = 0.8 if event.button == "up" else 1.25   # in shrinks the view
        ax = self._gps_ax_map
        xl, xr = ax.get_xlim(); yb, yt = ax.get_ylim()
        cx, cy = event.xdata, event.ydata
        ax.set_xlim(cx - (cx - xl) * scale, cx + (xr - cx) * scale)
        ax.set_ylim(cy - (cy - yb) * scale, cy + (yt - cy) * scale)
        self._gps_canvas.draw_idle()
        self._gps_schedule_nav()

    def _gps_schedule_nav(self):
        """Debounced: lock the user's view and refetch tiles at the right zoom."""
        if self._gps_nav_job is not None:
            try:
                self.after_cancel(self._gps_nav_job)
            except Exception:
                pass
        self._gps_nav_job = self.after(250, self._gps_apply_nav)

    def _gps_apply_nav(self):
        self._gps_view = (self._gps_ax_map.get_xlim(), self._gps_ax_map.get_ylim())
        self._update_gps_plots()

    def _gps_reset_view(self):
        """Return to the auto route-fit framing."""
        self._gps_view = None
        self._update_gps_plots()

    def _update_endpoints(self):
        if self._gps_endpoints is None or not len(getattr(self, "_gps_route_secs", [])):
            return
        xs, ys = self._endpoint_coords()
        self._gps_endpoints.set_offsets(np.column_stack([xs, ys]))

    def _update_window_label(self):
        if self._gps_t0 is None:
            self._gps_window_label.config(text="")
            return
        lo, hi = sorted(self._gps_marker_secs)
        t_lo = (self._gps_t0 + pd.Timedelta(seconds=lo)).strftime("%H:%M:%S")
        t_hi = (self._gps_t0 + pd.Timedelta(seconds=hi)).strftime("%H:%M:%S")
        dur  = hi - lo
        flag = "  [FILTER ON]" if getattr(self, "_time_filter", None) else ""
        self._gps_window_label.config(
            text=f"Window: {t_lo} – {t_hi}   (Δ {int(dur // 60)}:{int(dur % 60):02d}){flag}")

    # ── Filter buttons ───────────────────────────────────────────────────────
    def _gps_apply_filter(self):
        if self._gps_t0 is None:
            return
        lo, hi = sorted(self._gps_marker_secs)
        tmin = self._gps_t0 + pd.Timedelta(seconds=lo)
        tmax = self._gps_t0 + pd.Timedelta(seconds=hi)
        self._apply_time_filter(tmin, tmax)

    def _gps_clear_filter(self):
        self._clear_time_filter()

    # ── Global time filter (slices the cached full result for every tab) ──────
    # Both this window filter and the import-tab "Auto-Filter Out Stopped Times"
    # filter compose through calibration._recompute_filtered_view — set the
    # _time_filter state here and let that helper rebuild the view.
    def _apply_time_filter(self, tmin, tmax):
        if self._gps_base() is None:
            return
        self._time_filter = (tmin, tmax)
        self._recompute_filtered_view()

    def _clear_time_filter(self):
        if self._gps_base() is None:
            return
        self._time_filter = None
        self._recompute_filtered_view()

    # ── Small utilities ──────────────────────────────────────────────────────
    @staticmethod
    def _gps_cmap():
        import matplotlib as mpl
        cmap = mpl.colormaps[GPS_CMAP].copy()
        cmap.set_bad(BG)
        return cmap

    def _gps_time_formatter(self):
        """Elapsed-seconds axis (not a real datetime axis, so w.format_time_axis
        doesn't apply directly) — same HH:MM:SS.mmm rule as everywhere else,
        never day/month/year."""
        from matplotlib.ticker import FuncFormatter
        t0 = self._gps_t0
        def _fmt(x, _pos):
            try:
                dt = t0 + pd.Timedelta(seconds=float(x))
                return f"{dt:%H:%M:%S}.{dt.microsecond // 1000:03d}"
            except Exception:
                return ""
        return FuncFormatter(_fmt)
