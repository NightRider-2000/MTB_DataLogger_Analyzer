import matplotlib
matplotlib.use("TkAgg")

import tkinter as tk
from tkinter import ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from constants import BG, DARK, FIELD, BTN_FG, GRID


def make_btn(parent, text, command):
    return ttk.Button(parent, text=text, command=command, style="Dark.TButton")


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


def style_ax(ax):
    ax.tick_params(colors=DARK)
    ax.xaxis.label.set_color(DARK)
    ax.yaxis.label.set_color(DARK)
    ax.title.set_color(DARK)
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK)
    ax.grid(True, color=GRID, linewidth=0.7, linestyle="-")
    ax.set_axisbelow(True)
