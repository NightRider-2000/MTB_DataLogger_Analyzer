import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

import widgets as w
from constants import BG, DARK, HIST_COLORS

# Left panel selector colors — match the Time Series primary slots (red, blue, yellow).
_PSD_COLORS = [HIST_COLORS[0], HIST_COLORS[1], HIST_COLORS[3]]
_N_PSD_SIGS = 3

# Synthetic x-axis options for the PSD-vs-X map: row-wise average of both wheel
# speeds (skipna, listed first / default), and elapsed ride time (a classic
# spectrogram view — PSD evolution over the ride).
_AVG_SPEED_KEY = "Avg Wheel Speed (mph)"
_TIME_X_KEY    = "Time (s)"

# A gap this many nominal sample periods wide splits the series into separate
# contiguous segments before resampling (see _largest_contiguous_segment).
# Without this, one outlier gap (device left idle/paused mid-recording — seen
# for real as clean 4h/20h jumps in a ride log) makes pandas' resample() span
# the FULL calendar range regardless of how sparse the data actually is: a
# 20-hour gap in an otherwise-4ms-spaced ride turned a 116k-row series into a
# ~22M-row resampled one, which is what made this tab hang for ~47s.
_GAP_SEGMENT_FACTOR = 50

# Displayed frequency ceiling for BOTH panes. Real ride content lives well below
# the 120 Hz Nyquist, so showing 0–60 Hz doubles the useful plot area.
_FREQ_MAX_HZ = 60.0

# PSD-vs-X map parameters: STFT window (samples, at the ~240 Hz data rate;
# 1024 ≈ 4.3 s per column, ~0.23 Hz frequency resolution — bins sized to pair
# with the 60 Hz display ceiling) and x-axis bin count.
_SPEC_NPERSEG = 1024
_SPEC_X_BINS  = 40


class FrequencyMixin:

    def _build_frequency_tab(self):
        outer = tk.Frame(self.frequency_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        # PSD computation is opt-in (button below), not part of the automatic
        # load/calibration cascade — resample()-based frequency analysis over
        # a long ride is the single most expensive thing in the app, and most
        # sessions never look at this tab. Changing a selector recomputes
        # immediately once data is loaded (cheap after the gap-segmentation fix).
        btn_bar = tk.Frame(outer, bg=BG)
        btn_bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))
        w.make_btn(btn_bar, "Compute Frequency Analysis",
                  self._compute_frequency_plot).pack(side=tk.LEFT)
        self._freq_status_var = tk.StringVar(
            value="Click to compute — not run automatically (can take a while on long rides).")
        tk.Label(btn_bar, textvariable=self._freq_status_var, bg=BG, fg=DARK,
                anchor="w").pack(side=tk.LEFT, padx=12)

        panes = tk.Frame(outer, bg=BG)
        panes.pack(fill=tk.BOTH, expand=True)
        # uniform → both columns are forced to the SAME width (a strict 50/50
        # split); weight alone only splits the *extra* space equally, so the
        # pane with the wider selector row would otherwise end up wider.
        panes.columnconfigure(0, weight=1, uniform="freqpanes")
        panes.columnconfigure(1, weight=1, uniform="freqpanes")
        panes.rowconfigure(0, weight=1)

        # ── Left pane: PSD of up to 3 selectable signals ──────────────────────
        left = tk.Frame(panes, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(6, 3))
        sel_row = tk.Frame(left, bg=BG)
        sel_row.pack(side=tk.TOP, pady=(0, 2))
        self._psd_vars = []
        for j in range(_N_PSD_SIGS):
            tk.Label(sel_row, text="●", bg=BG, fg=_PSD_COLORS[j],
                     font=("", 15)).pack(side=tk.LEFT, padx=(6 if j else 0, 2))
            var = tk.StringVar()
            combo = ttk.Combobox(sel_row, textvariable=var, state="readonly", width=22)
            combo.pack(side=tk.LEFT, padx=(0, 4))
            combo.bind("<<ComboboxSelected>>", lambda e: self._freq_on_select())
            self._psd_vars.append(var)
        self._psd_combos = sel_row.winfo_children()[1::2]  # the comboboxes

        fig = w.make_figure(figsize=(6, 5), dpi=100)
        self._ax_psd = fig.add_subplot(111)
        self._ax_psd.set_facecolor(BG)
        canvas, cv_widget = w.make_canvas(fig, left)
        cv_widget.pack(fill=tk.BOTH, expand=True)
        self._freq_add_toolbar(canvas, left)
        self._fig_psd    = fig
        self._canvas_psd = canvas

        # ── Right pane: PSD-vs-X map (order analysis) ─────────────────────────
        right = tk.Frame(panes, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 6))
        sel_row2 = tk.Frame(right, bg=BG)
        sel_row2.pack(side=tk.TOP, pady=(0, 2))
        tk.Label(sel_row2, text="PSD of:", bg=BG, fg=DARK).pack(side=tk.LEFT)
        self._spec_y_var = tk.StringVar()
        self._spec_y_combo = ttk.Combobox(sel_row2, textvariable=self._spec_y_var,
                                          state="readonly", width=22)
        self._spec_y_combo.pack(side=tk.LEFT, padx=(2, 10))
        self._spec_y_combo.bind("<<ComboboxSelected>>", lambda e: self._freq_on_select())
        tk.Label(sel_row2, text="vs:", bg=BG, fg=DARK).pack(side=tk.LEFT)
        self._spec_x_var = tk.StringVar()
        self._spec_x_combo = ttk.Combobox(sel_row2, textvariable=self._spec_x_var,
                                          state="readonly", width=22)
        self._spec_x_combo.pack(side=tk.LEFT, padx=(2, 0))
        self._spec_x_combo.bind("<<ComboboxSelected>>", lambda e: self._freq_on_select())

        fig2 = w.make_figure(figsize=(6, 5), dpi=100)
        # Fixed map + colorbar axes (created once — recreating a colorbar with
        # fig.colorbar() on every recompute would stack new axes each time).
        gs = fig2.add_gridspec(1, 2, width_ratios=[30, 1], wspace=0.05)
        self._ax_spec = fig2.add_subplot(gs[0, 0])
        self._ax_spec.set_facecolor(BG)
        self._ax_spec_cbar = fig2.add_subplot(gs[0, 1])
        canvas2, cv_widget2 = w.make_canvas(fig2, right)
        cv_widget2.pack(fill=tk.BOTH, expand=True)
        self._freq_add_toolbar(canvas2, right)
        self._fig_spec    = fig2
        self._canvas_spec = canvas2

        self._freq_stale = True   # data changed since the plots were last computed

    @staticmethod
    def _freq_add_toolbar(canvas, parent):
        """Matplotlib navigation toolbar (rectangle-zoom, pan, home, save) under a
        plot — these are interactive analysis plots, so zooming is wanted here
        (unlike the Select Data quick-glance preview, which deliberately has none).
        Styled to the app background."""
        tb = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
        tb.config(background=BG)
        for child in tb.winfo_children():
            try:
                child.config(background=BG)
            except tk.TclError:
                pass
        tb.update()
        tb.pack(side=tk.BOTTOM, fill=tk.X)

    # ── Cascade hook (cheap) ──────────────────────────────────────────────────

    def _update_frequency_plot(self):
        """Called from the calibration refresh cascade — refreshes the selector
        lists and marks the plots stale (cheap) instead of recomputing. See
        _compute_frequency_plot, wired to the tab's button, for the actual
        (expensive) PSD work."""
        if not hasattr(self, "_ax_psd"):
            return
        self._freq_refresh_selectors()
        self._freq_stale = True
        if hasattr(self, "_freq_status_var"):
            self._freq_status_var.set(
                "Data changed — click Compute Frequency Analysis to refresh.")

    def _freq_refresh_selectors(self):
        """Populate the signal selectors from the loaded data, preserving any
        existing selections; seed defaults on first load."""
        if self.cal_result_df is None:
            return
        cols = [""] + list(self.cal_result_df.select_dtypes(include="number").columns)
        _defaults = ["Front_Wheel_Pos_mm", "Rear_Wheel_Pos_mm", "aVert_g"]
        for var, combo, default in zip(self._psd_vars, self._psd_combos, _defaults):
            current = var.get()
            combo["values"] = cols
            if not (current and current in cols):   # "" never counts as a kept selection
                var.set(default if default in cols else "")
        y_cols = cols[1:]
        cur_y = self._spec_y_var.get()
        self._spec_y_combo["values"] = y_cols
        if not (cur_y and cur_y in y_cols):
            self._spec_y_var.set("Rear_Wheel_Pos_mm" if "Rear_Wheel_Pos_mm" in y_cols else "")
        x_cols = [_AVG_SPEED_KEY, _TIME_X_KEY] + y_cols
        cur_x = self._spec_x_var.get()
        self._spec_x_combo["values"] = x_cols
        if not (cur_x and cur_x in x_cols):
            self._spec_x_var.set(_AVG_SPEED_KEY)

    def _freq_on_select(self):
        """Selector changed — recompute immediately if data is loaded (fast after
        the gap-segmentation fix); otherwise wait for the button."""
        if self.cal_result_df is not None:
            self._compute_frequency_plot()

    # ── Shared resample helpers ───────────────────────────────────────────────

    @staticmethod
    def _largest_contiguous_segment(series):
        """Split ``series`` at any gap wider than _GAP_SEGMENT_FACTOR nominal
        sample periods and return only the largest contiguous run. PSD/resample
        assumes one continuous, uniformly-sampled signal — silently resampling
        across a huge real-world gap (see module docstring) is both wrong
        (fabricates a discontinuity the frequency content doesn't have) and,
        for pandas' resample(), catastrophically slow."""
        dt_s = series.index.to_series().diff().dt.total_seconds()
        median_dt_s = float(dt_s.dropna().median()) if len(dt_s) > 1 else 0.0
        if not median_dt_s or median_dt_s <= 0:
            return series, median_dt_s
        gap_thresh_s = median_dt_s * _GAP_SEGMENT_FACTOR
        seg_id = (dt_s.fillna(0.0) > gap_thresh_s).cumsum()
        if seg_id.iloc[-1] == 0:   # no gaps — whole series is one segment
            return series, median_dt_s
        largest = seg_id.value_counts().idxmax()
        return series[seg_id == largest], median_dt_s

    def _freq_resampled(self, col):
        """Uniformly-resampled values of ``col`` over its largest contiguous
        segment. Returns ``(resampled_series, fs)`` or ``(None, 0)``."""
        series = self.cal_result_df[col].dropna()
        if len(series) < 128:
            return None, 0.0
        series, median_dt_s = self._largest_contiguous_segment(series)
        if not median_dt_s or median_dt_s <= 0 or len(series) < 128:
            return None, 0.0
        median_dt_ms = max(1, round(median_dt_s * 1000))
        # Interpolate only across gaps ≤ 2×dt (limit=1 fills 1 consecutive NaN)
        # Gaps > 2×dt stay NaN and are dropped — avoids interpolating across pauses
        resampled = series.resample(f"{median_dt_ms}ms").mean()
        resampled = resampled.interpolate(method="time", limit=1).dropna()
        if len(resampled) < 128:
            return None, 0.0
        return resampled, 1.0 / median_dt_s

    def _freq_x_series(self):
        """The selected x-axis signal for the PSD-vs-X map (synthetic avg-wheel-
        speed option or any numeric column), as a Series on cal_result_df's index."""
        key = self._spec_x_var.get()
        df = self.cal_result_df
        if key == _AVG_SPEED_KEY:
            cols = [c for c in ("Front_Horz_Wheel_Spd_mph", "Rear_Horz_Wheel_Spd_mph")
                    if c in df.columns]
            return df[cols].mean(axis=1) if cols else None
        if key == _TIME_X_KEY:
            import pandas as pd
            idx = df.index
            return pd.Series((idx - idx[0]).total_seconds(), index=idx)
        return df[key] if key in df.columns else None

    # ── The (expensive) compute, wired to the button + selectors ─────────────

    def _compute_frequency_plot(self):
        if not hasattr(self, "_ax_psd"):
            return
        if self.cal_result_df is None:
            self._freq_status_var.set("No data loaded.")
            return
        if not self._psd_vars[0].get() and not any(v.get() for v in self._psd_vars):
            self._freq_refresh_selectors()

        left_ok  = self._compute_psd_panel()
        right_ok = self._compute_spec_panel()

        self._freq_stale = False
        self._freq_status_var.set(
            "Up to date." if (left_ok or right_ok)
            else "No signal had enough data to analyze.")

    def _compute_psd_panel(self):
        """Left pane: overlaid PSDs of the selected signals."""
        ax = self._ax_psd
        ax.clear()
        ax.set_facecolor(BG)

        plotted = False
        for var, color in zip(self._psd_vars, _PSD_COLORS):
            col = var.get()
            if not col or col not in self.cal_result_df.columns:
                continue
            resampled, fs = self._freq_resampled(col)
            if resampled is None:
                continue
            values = resampled.values
            nfft = min(2048, 2 ** int(np.log2(len(values) // 4)))
            nfft = max(nfft, 128)

            pxx, freqs = ax.psd(values, NFFT=nfft, Fs=fs, noverlap=nfft // 2,
                                color=color, label=col, linewidth=1.2)
            plotted = True

            # Find peak above 1 Hz and annotate
            mask = freqs >= 1.0
            if mask.any():
                peak_idx  = np.argmax(pxx[mask])
                peak_freq = freqs[mask][peak_idx]
                peak_pwr  = 10 * np.log10(pxx[mask][peak_idx])  # dB for y position
                ax.axvline(peak_freq, color=color, linewidth=0.8, linestyle="--", alpha=0.7)
                ax.text(peak_freq, peak_pwr, f" {peak_freq:.2f} Hz",
                        color=color, fontsize=10, va="bottom")

        # Fixed 0.05–60 Hz frame (_FREQ_MAX_HZ): the signals are logged at 240 Hz
        # (Nyquist 120), but real ride content lives below 60 — halving the frame
        # doubles the useful resolution of the display.
        ax.set_xlim(0.05, _FREQ_MAX_HZ)
        ax.set_title("Power Spectral Density", color=DARK, fontsize=13)
        ax.set_xlabel("Frequency (Hz)", color=DARK, fontsize=12)
        ax.set_ylabel("Power/Frequency (dB/Hz)", color=DARK, fontsize=12)
        if plotted:
            ax.legend(fontsize=10, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
        w.style_ax(ax)

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fig_psd.tight_layout()
        self._canvas_psd.draw()
        return plotted

    def _compute_spec_panel(self):
        """Right pane: PSD-vs-X map (order analysis). Short-time FFT of the
        selected signal; each STFT column is tagged with the mean of the x-signal
        over its window; columns are binned by x and averaged (linear power) →
        a (frequency × x) power map. A speed-proportional excitation (wheel
        imbalance, tire knobs) appears as a DIAGONAL ridge when x is speed; a
        speed-independent one (steady-cadence pedal bob) appears HORIZONTAL."""
        from scipy.signal import spectrogram
        ax  = self._ax_spec
        cax = self._ax_spec_cbar
        ax.clear()
        cax.clear()
        ax.set_facecolor(BG)

        ycol = self._spec_y_var.get()
        x_series = self._freq_x_series()
        ok = False
        if ycol and ycol in self.cal_result_df.columns and x_series is not None:
            resampled, fs = self._freq_resampled(ycol)
            if resampled is not None:
                yv = resampled.values
                # Align x onto the resampled index POSITIONALLY (searchsorted) —
                # cal_result_df can carry duplicate timestamps (multi-file concat /
                # ms rounding), which makes reindex(method="nearest") raise. Then
                # ffill/bfill residual NaN.
                import pandas as pd
                xidx = x_series.index.values.astype("datetime64[ns]").astype(np.int64)
                ridx = resampled.index.values.astype("datetime64[ns]").astype(np.int64)
                pos = np.clip(np.searchsorted(xidx, ridx), 0, len(xidx) - 1)
                xv = pd.Series(x_series.values.astype(float)[pos]).ffill().bfill().values
                nper = min(_SPEC_NPERSEG, max(128, len(yv) // 8))
                nover = nper // 2
                freqs, times, sxx = spectrogram(yv, fs=fs, nperseg=nper,
                                                noverlap=nover, detrend="constant")
                # Trim to the displayed band up front — keeps the mesh small and
                # the robust color range computed only from what's actually shown.
                fkeep = freqs <= _FREQ_MAX_HZ
                freqs, sxx = freqs[fkeep], sxx[fkeep, :]
                step = nper - nover
                ncols = sxx.shape[1]
                # x value per STFT column = mean of x over that column's window
                xcol = np.array([np.nanmean(xv[k*step : k*step + nper])
                                 for k in range(ncols)])
                valid = np.isfinite(xcol)
                if valid.sum() >= 8:
                    lo, hi = np.nanmin(xcol[valid]), np.nanmax(xcol[valid])
                    if hi > lo:
                        # Time x-axis = a classic spectrogram: use many more bins
                        # (bounded by the STFT column count) so the ride's time
                        # structure isn't averaged away; value axes keep the
                        # coarser bins that make ridges (vs speed etc.) readable.
                        nbins = (min(400, max(_SPEC_X_BINS, ncols))
                                 if self._spec_x_var.get() == _TIME_X_KEY
                                 else _SPEC_X_BINS)
                        edges = np.linspace(lo, hi, nbins + 1)
                        idx = np.clip(np.digitize(xcol[valid], edges) - 1,
                                      0, nbins - 1)
                        psum = np.zeros((len(freqs), nbins))
                        cnt  = np.zeros(nbins)
                        np.add.at(psum.T, idx, sxx[:, valid].T)
                        np.add.at(cnt, idx, 1.0)
                        with np.errstate(divide="ignore", invalid="ignore"):
                            pmap = psum / cnt[None, :]
                            pdb  = 10.0 * np.log10(pmap)
                        pdb = np.ma.masked_invalid(pdb)
                        # Robust color range for contrast (1st–99th percentile)
                        vmin, vmax = np.nanpercentile(pdb.compressed(), [1, 99])
                        # pcolormesh wants EDGES on both axes; freqs are centers.
                        fstep  = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0
                        fedges = np.concatenate([freqs - fstep / 2,
                                                 [freqs[-1] + fstep / 2]])
                        mesh = ax.pcolormesh(edges, fedges, pdb, cmap="plasma",
                                             vmin=vmin, vmax=vmax, shading="flat")
                        cb = self._fig_spec.colorbar(mesh, cax=cax)
                        cb.set_label("Power (dB/Hz)", color=DARK)
                        cb.ax.tick_params(colors=DARK)
                        for lbl in cb.ax.get_yticklabels():
                            lbl.set_color(DARK)
                        ok = True

        if not ok:
            ax.text(0.5, 0.5, "No Data Available", transform=ax.transAxes,
                    ha="center", va="center", color=DARK, fontsize=14)
            cax.set_visible(False)
        else:
            cax.set_visible(True)
            ax.set_ylim(0, _FREQ_MAX_HZ)   # matches the left pane's frame
        ax.set_title(f"PSD of {ycol or '—'} vs {self._spec_x_var.get() or '—'}",
                     color=DARK, fontsize=13)
        ax.set_xlabel(self._spec_x_var.get(), color=DARK, fontsize=12)
        ax.set_ylabel("Frequency (Hz)", color=DARK, fontsize=12)
        w.style_ax(ax)
        ax.grid(False)   # gridlines on top of a dense colormap just add noise

        self._canvas_spec.draw()
        return ok
