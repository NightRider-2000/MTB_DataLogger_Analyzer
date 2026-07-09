import warnings

import widgets as w
from constants import BG, DARK, HIST_BAR_COLOR, HIST_COLORS, GRID


class PlotsMixin:

    def on_signal_select(self, event):
        if self.df is None:
            return
        selected = [self.signal_listbox.get(i) for i in self.signal_listbox.curselection()]
        self.plot_signals(selected)
        self.plot_histogram(selected)

    def plot_signals(self, columns):
        self.ax.clear()
        self.ax.set_facecolor(BG)
        if not columns or self.df is None:
            self.ax.set_title("No data / no signals selected", color=DARK)
            self.canvas.draw()
            return
        # Per-column, not one bulk DataFrame.plot() call — sparse raw signals
        # (GPS fixes, trigger-driven wheel speed: >90% NaN) need dot markers
        # or a connected line is either invisible or misleadingly continuous.
        for i, col in enumerate(columns):
            w.plot_time_series_smart(self.ax, self.df[col],
                                     color=HIST_COLORS[i % len(HIST_COLORS)], label=col)
        # Always pin the x-axis to the ride's real time range — an all-NaN
        # signal otherwise leaves matplotlib's default 0..1 axis in place,
        # which renders as garbled dates on a datetime axis.
        self.ax.set_xlim(self.df.index.min(), self.df.index.max())
        if self.df[columns].isna().all().all():
            self.ax.text(0.5, 0.5, "No Data Available", transform=self.ax.transAxes,
                         ha="center", va="center", color=DARK, fontsize=14)
        elif len(columns) > 1:
            self.ax.legend(fontsize=10, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
        title = "Time Series (raw)"
        if "rtcDate" in self.df.columns:
            date_val = self.df["rtcDate"].dropna().max()
            if date_val is not None:
                title += f"  —  {date_val}"
        try:
            duration_min = (self.df.index.max() - self.df.index.min()).total_seconds() / 60
            title = f"Duration: {duration_min:.2f} min\n{title}"
        except Exception:
            pass
        self.ax.set_title(title, color=DARK)
        self.ax.set_xlabel("Time", color=DARK)
        self.ax.set_ylabel("Value", color=DARK)
        w.style_ax(self.ax)
        w.format_time_axis(self.ax)
        self.fig.autofmt_xdate()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig.tight_layout()
        self.canvas.draw()

    def plot_histogram(self, columns):
        self.ax_hist.clear()
        self.ax_hist.set_facecolor(BG)
        if not columns or self.df is None:
            self.ax_hist.set_title("Select a signal", color=DARK)
            w.style_ax(self.ax_hist)
            self.canvas_hist.draw()
            return

        stats_lines = []
        for i, col in enumerate(columns):
            color = HIST_BAR_COLOR
            data  = self.df[col].dropna()
            if data.empty:
                continue
            mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
            self.ax_hist.hist(data, bins=200, alpha=0.45, color=color, label=col)
            self.ax_hist.axvline(mean, color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
            self.ax_hist.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvspan(mean - std, mean + std, alpha=0.12, color=color)
            stats_lines.append(
                f"{col}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}"
            )

        if stats_lines:
            self.ax_hist.text(
                0.97, 0.97, "\n\n".join(stats_lines),
                transform=self.ax_hist.transAxes, fontsize=10,
                verticalalignment="top", horizontalalignment="right", color=DARK,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9),
            )
        else:
            self.ax_hist.text(0.5, 0.5, "No Data Available",
                              transform=self.ax_hist.transAxes,
                              ha="center", va="center", color=DARK, fontsize=14)
        self.ax_hist.set_title("Histogram", color=DARK)
        self.ax_hist.set_xlabel("Value", color=DARK)
        self.ax_hist.set_ylabel("Count", color=DARK)
        if len(columns) > 1:
            # upper left: the stats box above occupies upper right
            self.ax_hist.legend(fontsize=10, loc="upper left")
        w.style_ax(self.ax_hist)
        self.canvas_hist.draw()
