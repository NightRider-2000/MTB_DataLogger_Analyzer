import matplotlib
matplotlib.use("TkAgg")

import time
import tkinter as tk
from tkinter import ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from constants import BG, DARK, FIELD, BTN_FG, GRID


def make_btn(parent, text, command, style="Dark.TButton"):
    return ttk.Button(parent, text=text, command=command, style=style)


def enable_gridlines(tree):
    """RULE: call on every ttk.Treeview after its columns are configured.
    Turns on Tk 9 native column separators (vertical grey cell borders); the
    horizontal rules come from the shared Row layout in theme.py. No-op on
    pre-9 Tk."""
    try:
        for cid in tree["columns"]:
            tree.column(cid, separator=True)
    except tk.TclError:
        pass


def make_entry(parent, width=10):
    return tk.Entry(
        parent, width=width,
        bg=FIELD, fg=DARK,
        insertbackground=DARK,
        highlightbackground=DARK, highlightcolor=DARK, highlightthickness=1,
        relief="flat",
    )


def make_listbox(parent, selectmode=tk.EXTENDED):
    return tk.Listbox(
        parent,
        selectmode=selectmode,
        exportselection=False,
        bg=FIELD, fg=DARK,
        selectbackground=DARK, selectforeground=BTN_FG,
        highlightbackground=DARK, highlightthickness=1,
        relief="flat", bd=0,
    )


def make_figure(**kwargs):
    fig = Figure(**kwargs)
    fig.patch.set_facecolor(BG)
    return fig


def make_canvas(fig, parent):
    canvas = FigureCanvasTkAgg(fig, master=parent)
    widget = canvas.get_tk_widget()
    widget.config(width=1, height=1)
    return canvas, widget


def sample_period_s(index):
    """Median sample period (seconds) of a DatetimeIndex, or None if undeterminable.
    The logger runs at a fixed rate (currently 240 Hz) but the rate is NEVER
    hardcoded — always derive it from the loaded data's time index."""
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return None
    dt  = index.to_series().diff().dt.total_seconds()
    med = dt[dt > 0].median()
    return float(med) if med and med > 0 else None


def sample_rate_hz(index):
    """Median sample rate (Hz) of a DatetimeIndex, or None if undeterminable."""
    p = sample_period_s(index)
    return (1.0 / p) if p else None


def insert_gap_nans(data, max_gap_s=1.0):
    """Insert NaN rows where the DatetimeIndex gap exceeds max_gap_s seconds.
    Accepts a DataFrame or Series. Non-datetime indexes are returned unchanged."""
    if not isinstance(data.index, pd.DatetimeIndex):
        return data
    diffs   = data.index.to_series().diff()
    gap_idx = diffs[diffs > pd.Timedelta(seconds=max_gap_s)].index
    if gap_idx.empty:
        return data
    if isinstance(data, pd.Series):
        nans = pd.Series(float("nan"),
                         index=gap_idx - pd.Timedelta(nanoseconds=1),
                         name=data.name)
    else:
        nans = pd.DataFrame(float("nan"),
                            index=gap_idx - pd.Timedelta(nanoseconds=1),
                            columns=data.columns)
    return pd.concat([data, nans]).sort_index()


class ProgressDialog:
    """Modal 'please wait' window for a long-running, step-based operation
    (CSV import, the full calibration cascade). Shows a determinate progress
    bar, a status label naming the current step, and a live elapsed/estimated-
    remaining time readout.

    Tk is single-threaded: the caller must do the actual work in a sequence
    of chunks (one CSV file, one calibration stage) and call .step(...) after
    each chunk completes — that call both updates the bar and pumps Tk's
    event loop so the window repaints and the app doesn't look frozen. Don't
    call this from inside a single giant blocking call; break the work up.
    """

    def __init__(self, parent, title="Please wait…"):
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.configure(bg=BG)
        self.win.transient(parent)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", lambda: None)   # no close button
        self.label = tk.Label(self.win, text=title, bg=BG, fg=DARK,
                              anchor="w", width=44)
        self.label.pack(padx=16, pady=(16, 6), fill=tk.X)
        self.bar = ttk.Progressbar(self.win, mode="determinate",
                                   maximum=100, length=340)
        self.bar.pack(padx=16, pady=(0, 6))
        self.time_label = tk.Label(self.win, text="", bg=BG, fg=DARK, anchor="w")
        self.time_label.pack(padx=16, pady=(0, 16), fill=tk.X)

        self.win.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.win.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.win.winfo_height()) // 3
        self.win.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        self.win.grab_set()   # modal — block interaction with the rest of the app

        self._t0 = time.monotonic()
        self.win.update()

    def step(self, label, frac):
        """Advance the bar to ``frac`` (0..1) and show ``label`` as the
        current step. Call after each chunk of work completes."""
        self.label.configure(text=label)
        self.bar["value"] = max(0.0, min(1.0, frac)) * 100
        elapsed = time.monotonic() - self._t0
        if 0 < frac < 1:
            remaining = elapsed * (1 - frac) / frac
            self.time_label.configure(
                text=f"{elapsed:.1f}s elapsed  •  ~{remaining:.1f}s remaining")
        else:
            self.time_label.configure(text=f"{elapsed:.1f}s elapsed")
        self.win.update()   # repaint + pump events so the UI stays live

    def close(self):
        self.win.grab_release()
        self.win.destroy()


def plot_time_series_smart(ax, series, color=None, label=None):
    """Plot a time-indexed Series using the project's sparse-signal convention:
    if it's >50% NaN after gap insertion (GPS fixes, trigger-driven wheel
    speed, etc.), draw dots (linestyle="none", marker=".", markersize=3) —
    a connected line across mostly-missing data is either invisible (no two
    valid samples are ever adjacent) or misleadingly implies continuity.
    Dense signals get a normal connected line. Always call this rather than
    a bare .plot()/ax.plot() wherever a raw or calibrated time-domain signal
    might be sparse."""
    gapped = insert_gap_nans(series)
    sparse = gapped.dropna()
    nan_frac = 1 - len(sparse) / max(len(gapped), 1)
    if nan_frac > 0.5:
        ax.plot(sparse.index, sparse.values, color=color, label=label,
                linestyle="none", marker=".", markersize=3)
    else:
        ax.plot(gapped.index, gapped.values, color=color, label=label)


def format_time_axis(ax):
    """RULE: call on every x-axis whose ticks represent time-of-day (a real
    datetime axis — a pandas DatetimeIndex plotted directly, e.g. via
    plot_time_series_smart). Tick labels are always HH:MM:SS.mmm — NEVER
    day/month/year — overriding matplotlib's default date locator/formatter,
    which otherwise shows a date once the axis is zoomed out far enough.
    Do NOT call this on non-time axes (histograms, free-scatter plots of two
    arbitrary signals, frequency/PSD plots, etc.) — those aren't time axes
    and this would just print garbage tick labels."""
    import matplotlib.dates as mdates
    from matplotlib.ticker import FuncFormatter

    def _fmt(x, _pos):
        try:
            dt = mdates.num2date(x)
            return f"{dt:%H:%M:%S}.{dt.microsecond // 1000:03d}"
        except Exception:
            return ""
    ax.xaxis.set_major_formatter(FuncFormatter(_fmt))


def plot_hist_line(ax, data, bins, color, label=None, linewidth=1.5):
    """Draw a histogram as a LINE, not bars: bin the data with np.histogram, then
    plot bin CENTERS vs counts as straight line segments (a frequency polygon —
    no curve smoothing), closed to zero at both ends so it reads as a bounded
    distribution. Call this everywhere instead of ax.hist() for a 1-D histogram.

    ``bins`` may be an int or an array of edges (passed straight to np.histogram,
    so callers can share edges across overlaid signals). Returns
    ``(counts, bin_edges)`` — same leading tuple as ax.hist() — for callers that
    need them (e.g. percentile-zoom y-scaling)."""
    import numpy as np
    vals = np.asarray(data, dtype=float)
    vals = vals[np.isfinite(vals)]
    edges = np.histogram_bin_edges(vals if vals.size else [0.0, 1.0], bins=bins)
    if vals.size == 0:
        return np.array([]), edges
    counts, edges = np.histogram(vals, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    # Close the polygon down to zero at the outer bin edges.
    xs = np.concatenate(([edges[0]], centers, [edges[-1]]))
    ys = np.concatenate(([0.0], counts.astype(float), [0.0]))
    ax.plot(xs, ys, color=color, label=label, linewidth=linewidth)
    return counts, edges


def shared_bin_edges(datasets, bins):
    """Common histogram bin edges spanning the combined finite range of several
    datasets. **RULE — whenever 2+ histograms are drawn on the same Axes, bin
    them on the SAME edges:** compute the edges once with this, then pass the
    returned array to every ``plot_hist_line`` call on that Axes, so the overlaid
    distributions are directly comparable bin-for-bin (independent per-signal
    bins would misalign the lines and misrepresent overlap). ``bins`` is passed
    to ``np.histogram_bin_edges`` (an int count, or a rule name)."""
    import numpy as np
    arrs = [np.asarray(d, dtype=float).ravel() for d in datasets]
    allv = np.concatenate(arrs) if arrs else np.array([0.0, 1.0])
    allv = allv[np.isfinite(allv)]
    if allv.size == 0:
        allv = np.array([0.0, 1.0])
    return np.histogram_bin_edges(allv, bins=bins)


def style_ax(ax):
    ax.tick_params(colors=DARK)
    ax.xaxis.label.set_color(DARK)
    ax.yaxis.label.set_color(DARK)
    ax.title.set_color(DARK)
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK)
    ax.grid(True, color=GRID, linewidth=0.7, linestyle="-")
    ax.set_axisbelow(True)
    for lbl in ax.get_xticklabels():
        lbl.set_rotation(0)
        lbl.set_ha("center")
