import tkinter as tk

import numpy as np

import widgets as w
from constants import BG, DARK, HIST_COLORS

_FRONT_COLOR = HIST_COLORS[0]
_REAR_COLOR  = HIST_COLORS[1]

# A gap this many nominal sample periods wide splits the series into separate
# contiguous segments before resampling (see _update_frequency_plot). Without
# this, one outlier gap (device left idle/paused mid-recording — seen for real
# as clean 4h/20h jumps in a ride log) makes pandas' resample() span the FULL
# calendar range regardless of how sparse the data actually is: a 20-hour gap
# in an otherwise-4ms-spaced ride turned a 116k-row series into a ~22M-row
# resampled one, which is what made this tab hang for ~47s.
_GAP_SEGMENT_FACTOR = 50


class FrequencyMixin:

    def _build_frequency_tab(self):
        outer = tk.Frame(self.frequency_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        # PSD computation is opt-in (button below), not part of the automatic
        # load/calibration cascade — resample()-based frequency analysis over
        # a long ride is the single most expensive thing in the app, and most
        # sessions never look at this tab.
        btn_bar = tk.Frame(outer, bg=BG)
        btn_bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))
        w.make_btn(btn_bar, "Compute Frequency Analysis",
                  self._compute_frequency_plot).pack(side=tk.LEFT)
        self._freq_status_var = tk.StringVar(
            value="Click to compute — not run automatically (can take a while on long rides).")
        tk.Label(btn_bar, textvariable=self._freq_status_var, bg=BG, fg=DARK,
                anchor="w").pack(side=tk.LEFT, padx=12)

        fig = w.make_figure(figsize=(12, 6), dpi=100)
        self._ax_psd = fig.add_subplot(111)
        self._ax_psd.set_facecolor(BG)

        canvas, cv_widget = w.make_canvas(fig, outer)
        cv_widget.pack(fill=tk.BOTH, expand=True)

        self._fig_psd    = fig
        self._canvas_psd = canvas
        self._freq_stale = True   # data changed since the plot was last computed

    def _update_frequency_plot(self):
        """Called from the calibration refresh cascade — just marks the plot
        stale (cheap) instead of recomputing. See _compute_frequency_plot,
        wired to the tab's button, for the actual (expensive) PSD work."""
        if not hasattr(self, "_ax_psd"):
            return
        self._freq_stale = True
        if hasattr(self, "_freq_status_var"):
            self._freq_status_var.set(
                "Data changed — click Compute Frequency Analysis to refresh.")

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

    def _compute_frequency_plot(self):
        if not hasattr(self, "_ax_psd"):
            return
        if self.cal_result_df is None:
            self._freq_status_var.set("No data loaded.")
            return

        ax = self._ax_psd
        ax.clear()
        ax.set_facecolor(BG)

        plotted = False
        for col, color, label in [
            ("Front_Wheel_Pos_mm", _FRONT_COLOR,   "Front Wheel Pos"),
            ("Rear_Wheel_Pos_mm",  _REAR_COLOR,    "Rear Wheel Pos"),
            ("aVert_g",            HIST_COLORS[2], "Vert Accel"),
        ]:
            if col not in self.cal_result_df.columns:
                continue
            series = self.cal_result_df[col].dropna()
            if len(series) < 128:
                continue

            series, median_dt_s = self._largest_contiguous_segment(series)
            if not median_dt_s or median_dt_s <= 0 or len(series) < 128:
                continue
            median_dt_ms = max(1, round(median_dt_s * 1000))

            # Interpolate only across gaps ≤ 2×dt (limit=1 fills 1 consecutive NaN)
            # Gaps > 2×dt stay NaN and are dropped — avoids interpolating across pauses
            resampled = series.resample(f"{median_dt_ms}ms").mean()
            resampled = resampled.interpolate(method="time", limit=1)
            resampled = resampled.dropna()
            if len(resampled) < 128:
                continue

            fs = 1.0 / median_dt_s
            values = resampled.values
            nfft = min(2048, 2 ** int(np.log2(len(values) // 4)))
            nfft = max(nfft, 128)

            pxx, freqs = ax.psd(values, NFFT=nfft, Fs=fs, noverlap=nfft // 2,
                                color=color, label=label, linewidth=1.2)
            plotted = True

            # Find peak above 1 Hz and annotate
            mask = freqs >= 1.0
            if mask.any():
                peak_idx  = np.argmax(pxx[mask])
                peak_freq = freqs[mask][peak_idx]
                peak_pwr  = 10 * np.log10(pxx[mask][peak_idx])  # convert to dB for y position
                ax.axvline(peak_freq, color=color, linewidth=0.8, linestyle="--", alpha=0.7)
                ax.text(peak_freq, peak_pwr, f" {peak_freq:.2f} Hz",
                        color=color, fontsize=10, va="bottom")

        # Fixed 0-120 Hz frame: these signals are logged at 240 Hz, so 120 Hz
        # IS the Nyquist limit — nothing above it can be real content anyway.
        ax.set_xlim(0.05, 120)
        ax.set_title("Power Spectral Density — Wheel Position", color=DARK, fontsize=13)
        ax.set_xlabel("Frequency (Hz)", color=DARK, fontsize=12)
        ax.set_ylabel("Power/Frequency (dB/Hz)", color=DARK, fontsize=12)
        if plotted:
            ax.legend(fontsize=12, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
        w.style_ax(ax)

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fig_psd.tight_layout()
        self._canvas_psd.draw()

        self._freq_stale = False
        self._freq_status_var.set(
            "Up to date." if plotted else "No signal had enough data to analyze.")
