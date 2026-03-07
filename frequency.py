import tkinter as tk

import numpy as np

import widgets as w
from constants import BG, DARK, HIST_COLORS

_FRONT_COLOR = HIST_COLORS[0]
_REAR_COLOR  = HIST_COLORS[1]


class FrequencyMixin:

    def _build_frequency_tab(self):
        outer = tk.Frame(self.frequency_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        fig = w.make_figure(figsize=(12, 6), dpi=100)
        self._ax_psd = fig.add_subplot(111)
        self._ax_psd.set_facecolor(BG)

        canvas, cv_widget = w.make_canvas(fig, outer)
        cv_widget.pack(fill=tk.BOTH, expand=True)

        self._fig_psd    = fig
        self._canvas_psd = canvas

    def _update_frequency_plot(self):
        if not hasattr(self, "_ax_psd"):
            return
        if self.cal_result_df is None:
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

            # Compute median dt; resample to uniform grid
            _dt_s = series.index.to_series().diff().dt.total_seconds().dropna()
            median_dt_s = float(_dt_s.median())
            if median_dt_s <= 0:
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
                        color=color, fontsize=7, va="bottom")

        ax.set_xlim(left=0.05)
        ax.set_title("Power Spectral Density — Wheel Position", color=DARK, fontsize=9)
        ax.set_xlabel("Frequency (Hz)", color=DARK, fontsize=8)
        ax.set_ylabel("Power/Frequency (dB/Hz)", color=DARK, fontsize=8)
        if plotted:
            ax.legend(fontsize=8, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
        w.style_ax(ax)

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fig_psd.tight_layout()
        self._canvas_psd.draw()
