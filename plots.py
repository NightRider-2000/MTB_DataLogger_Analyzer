import widgets as w
from constants import BG, DARK, HIST_BAR_COLOR, GRID


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
        w.insert_gap_nans(self.df[columns]).plot(ax=self.ax)
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
        self.fig.autofmt_xdate()
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
            mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
            self.ax_hist.hist(data, bins=200, alpha=0.55, color=color, label=col)
            self.ax_hist.axvline(mean, color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
            self.ax_hist.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist.axvspan(mean - std, mean + std, alpha=0.12, color=color)
            stats_lines.append(
                f"{col}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}"
            )

        self.ax_hist.text(
            0.97, 0.97, "\n\n".join(stats_lines),
            transform=self.ax_hist.transAxes, fontsize=7,
            verticalalignment="top", horizontalalignment="right", color=DARK,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9),
        )
        self.ax_hist.set_title("Histogram", color=DARK)
        self.ax_hist.set_xlabel("Value", color=DARK)
        self.ax_hist.set_ylabel("Count", color=DARK)
        if len(columns) > 1:
            self.ax_hist.legend(fontsize=7)
        w.style_ax(self.ax_hist)
        self.canvas_hist.draw()
