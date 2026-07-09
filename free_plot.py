import tkinter as tk
import warnings
from tkinter import ttk

import numpy as np

import widgets as w
from constants import BG, DARK, GRID, TREND_COLOR, BIN_MEAN_COLOR


class FreePlotMixin:

    def _build_free_plot_tab(self):
        frame = tk.Frame(self.free_plot_tab, bg=BG)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        # ── Left: axis selectors ─────────────────────────────────────────────
        left = tk.Frame(frame, bg=BG)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        for label, attr in [
            ("X-Axis",     "fp_x_var"),
            ("Y-Axis",     "fp_y_var"),
            ("Color-Axis", "fp_c_var"),
        ]:
            tk.Label(left, text=label, bg=BG, fg=DARK).pack(anchor="w", pady=(10, 2))
            var = tk.StringVar()
            setattr(self, attr, var)
            cb = ttk.Combobox(left, textvariable=var, state="readonly", width=22)
            cb.pack(anchor="w")
            cb.bind("<<ComboboxSelected>>", self._update_free_plot)
            attr_cb = attr.replace("_var", "_combo")
            setattr(self, attr_cb, cb)

        # ── Right: plot canvas ───────────────────────────────────────────────
        right = tk.Frame(frame, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.fig_fp  = w.make_figure(figsize=(8, 6), dpi=100)
        self.ax_fp   = self.fig_fp.add_subplot(111)
        self.ax_fp.set_facecolor(BG)
        self.canvas_fp, fp_widget = w.make_canvas(self.fig_fp, right)
        fp_widget.grid(row=0, column=0, sticky="nsew")
        self.canvas_fp.draw()

    def _refresh_free_plot_signals(self):
        if not hasattr(self, "fp_x_combo"):
            return
        if self.cal_result_df is None:
            return
        cols = [""] + list(self.cal_result_df.columns)
        for attr in ("fp_x_combo", "fp_y_combo", "fp_c_combo"):
            cb = getattr(self, attr)
            current = cb.get()
            cb["values"] = cols
            if current in cols:
                cb.set(current)
            else:
                cb.set("")

    def _update_free_plot(self, event=None):
        if self.cal_result_df is None:
            return
        x_col = self.fp_x_var.get()
        y_col = self.fp_y_var.get()
        c_col = self.fp_c_var.get()

        self.fig_fp.clear()
        self.ax_fp = self.fig_fp.add_subplot(111)
        self.ax_fp.set_facecolor(BG)

        if not x_col or not y_col:
            w.style_ax(self.ax_fp)
            self.canvas_fp.draw()
            return

        x = self.cal_result_df[x_col].dropna()
        y = self.cal_result_df[y_col].dropna()
        idx = x.index.intersection(y.index)

        if c_col and c_col in self.cal_result_df.columns:
            c_series = self.cal_result_df[c_col].dropna()
            idx = idx.intersection(c_series.index)
            xv = x[idx].values.astype(float)
            yv = y[idx].values.astype(float)
            cv = c_series[idx].values.astype(float)
            sc = self.ax_fp.scatter(xv, yv, c=cv, cmap="plasma",
                                    s=8, alpha=0.5, linewidths=0)
            cbar = self.fig_fp.colorbar(sc, ax=self.ax_fp)
            cbar.set_label(c_col, color=DARK)
            cbar.ax.yaxis.set_tick_params(color=DARK)
            for lbl in cbar.ax.get_yticklabels():
                lbl.set_color(DARK)
        else:
            xv = x[idx].values.astype(float)
            yv = y[idx].values.astype(float)
            self.ax_fp.scatter(xv, yv, s=8, alpha=0.5,
                               color=DARK, linewidths=0)

        # ── Trend line (linear regression) ───────────────────────────────────
        if len(xv) > 1:
            m, b = np.polyfit(xv, yv, 1)
            y_pred = m * xv + b
            ss_res = np.sum((yv - y_pred) ** 2)
            ss_tot = np.sum((yv - yv.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
            x_line = np.array([xv.min(), xv.max()])
            sign = "+" if b >= 0 else "-"
            eq_label = f"y = {m:.3g}x {sign} {abs(b):.3g}   R²={r2:.3f}"
            self.ax_fp.plot(x_line, m * x_line + b,
                            color=TREND_COLOR, linewidth=1.8,
                            linestyle="--", label=eq_label, zorder=5)

        # ── Binned mean ± std (20 bins across x range) ───────────────────────
        if len(xv) > 20:
            bins = np.linspace(xv.min(), xv.max(), 21)
            bin_centers, bin_means, bin_stds = [], [], []
            for lo, hi in zip(bins[:-1], bins[1:]):
                mask = (xv >= lo) & (xv < hi)
                if mask.sum() > 0:
                    bin_centers.append((lo + hi) / 2)
                    bin_means.append(yv[mask].mean())
                    bin_stds.append(yv[mask].std())
            if bin_centers:
                bc = np.array(bin_centers)
                bm = np.array(bin_means)
                bs = np.array(bin_stds)
                self.ax_fp.plot(bc, bm, color=BIN_MEAN_COLOR, linewidth=2.0,
                                marker="o", markersize=5, label="Bin mean", zorder=6)
                self.ax_fp.fill_between(bc, bm - bs, bm + bs,
                                        alpha=0.20, color=BIN_MEAN_COLOR, label="±1σ")

        self.ax_fp.legend(fontsize=12, facecolor=BG, edgecolor=DARK, labelcolor=DARK)
        self.ax_fp.set_xlabel(x_col, color=DARK)
        self.ax_fp.set_ylabel(y_col, color=DARK)
        self.ax_fp.set_title(f"{y_col} vs {x_col}", color=DARK)
        w.style_ax(self.ax_fp)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig_fp.tight_layout()
        self.canvas_fp.draw()
