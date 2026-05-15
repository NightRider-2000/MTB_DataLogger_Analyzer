import tkinter as tk
import warnings
from tkinter import ttk

import widgets as w
from constants import BG, DARK, GRID, HIST_COLORS


class FreeHistogramMixin:

    def _build_free_histogram_tab(self):
        frame = tk.Frame(self.free_histogram_tab, bg=BG)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        # ── Left: signal selectors ────────────────────────────────────────────
        left = tk.Frame(frame, bg=BG)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        self.fh_sig_vars   = []
        self.fh_sig_combos = []
        for i in range(1, 5):
            tk.Label(left, text=f"Signal {i}", bg=BG, fg=DARK).pack(anchor="w", pady=(10, 2))
            var = tk.StringVar()
            cb  = ttk.Combobox(left, textvariable=var, state="readonly", width=22)
            cb.pack(anchor="w")
            cb.bind("<<ComboboxSelected>>", self._update_free_histogram)
            self.fh_sig_vars.append(var)
            self.fh_sig_combos.append(cb)

        tk.Frame(left, bg=GRID, height=1).pack(fill=tk.X, pady=(14, 0))
        tk.Label(left, text="Y Axis (2D mode)", bg=BG, fg=DARK).pack(anchor="w", pady=(8, 2))
        self.fh_y_var   = tk.StringVar()
        self.fh_y_combo = ttk.Combobox(left, textvariable=self.fh_y_var, state="readonly", width=22)
        self.fh_y_combo.pack(anchor="w")
        self.fh_y_combo.bind("<<ComboboxSelected>>", self._update_free_histogram)

        tk.Label(left, text="(uses Signal 1 as X;\nSignals 2–4 ignored)",
                 bg=BG, fg=GRID, font=("TkDefaultFont", 8),
                 justify="left").pack(anchor="w", pady=(4, 0))

        # ── Right: plot canvas ────────────────────────────────────────────────
        right = tk.Frame(frame, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.fig_fh  = w.make_figure(figsize=(8, 6), dpi=100)
        self.ax_fh   = self.fig_fh.add_subplot(111)
        self.ax_fh.set_facecolor(BG)
        self.canvas_fh, fh_widget = w.make_canvas(self.fig_fh, right)
        fh_widget.grid(row=0, column=0, sticky="nsew")
        self.canvas_fh.draw()

    def _refresh_free_histogram_signals(self):
        if not hasattr(self, "fh_sig_combos"):
            return
        if self.cal_result_df is None:
            return
        cols = [""] + list(self.cal_result_df.columns)
        for cb, var in zip(self.fh_sig_combos, self.fh_sig_vars):
            cur = cb.get()
            cb["values"] = cols
            cb.set(cur if cur in cols else "")
        cur_y = self.fh_y_combo.get()
        self.fh_y_combo["values"] = cols
        self.fh_y_combo.set(cur_y if cur_y in cols else "")

    def _update_free_histogram(self, event=None):
        if self.cal_result_df is None:
            return

        self.fig_fh.clear()
        self.ax_fh = self.fig_fh.add_subplot(111)
        self.ax_fh.set_facecolor(BG)

        y_col = self.fh_y_var.get()

        if y_col:
            # ── 2D histogram mode (Signal 1 = X, Y Axis = Y) ─────────────────
            x_col = self.fh_sig_vars[0].get()
            if not x_col or x_col not in self.cal_result_df.columns:
                w.style_ax(self.ax_fh)
                self.canvas_fh.draw()
                return
            if y_col not in self.cal_result_df.columns:
                w.style_ax(self.ax_fh)
                self.canvas_fh.draw()
                return

            xv = self.cal_result_df[x_col].dropna()
            yv = self.cal_result_df[y_col].dropna()
            idx = xv.index.intersection(yv.index)
            xv  = xv[idx].values.astype(float)
            yv  = yv[idx].values.astype(float)

            if len(xv) < 2:
                w.style_ax(self.ax_fh)
                self.canvas_fh.draw()
                return

            _, _, _, img = self.ax_fh.hist2d(xv, yv, bins=100, cmap="hot")
            cbar = self.fig_fh.colorbar(img, ax=self.ax_fh)
            cbar.set_label("Count", color=DARK)
            cbar.ax.yaxis.set_tick_params(color=DARK)
            for lbl in cbar.ax.get_yticklabels():
                lbl.set_color(DARK)
            self.ax_fh.set_xlabel(x_col, color=DARK)
            self.ax_fh.set_ylabel(y_col, color=DARK)
            self.ax_fh.set_title(f"{y_col} vs {x_col}  (2D density)", color=DARK)

        else:
            # ── 1D overlay histogram mode ─────────────────────────────────────
            plotted = False
            stats_lines = []
            for i, (var, color) in enumerate(zip(self.fh_sig_vars, HIST_COLORS)):
                col = var.get()
                if not col or col not in self.cal_result_df.columns:
                    continue
                data = self.cal_result_df[col].dropna()
                if data.empty:
                    continue
                mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
                self.ax_fh.hist(data.values.astype(float), bins=200,
                                alpha=0.45, color=color, label=col)
                self.ax_fh.axvline(mean, color=color, linestyle="--", linewidth=1.5)
                self.ax_fh.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
                self.ax_fh.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
                self.ax_fh.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
                self.ax_fh.axvspan(mean - std, mean + std, alpha=0.12, color=color)
                stats_lines.append(
                    f"{col}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}"
                )
                plotted = True

            if plotted:
                self.ax_fh.text(
                    0.97, 0.97, "\n\n".join(stats_lines),
                    transform=self.ax_fh.transAxes, fontsize=7,
                    verticalalignment="top", horizontalalignment="right", color=DARK,
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9),
                )
                handles, _ = self.ax_fh.get_legend_handles_labels()
                if handles:
                    self.ax_fh.legend(fontsize=8, facecolor=BG,
                                      edgecolor=DARK, labelcolor=DARK)
                self.ax_fh.set_xlabel("Value", color=DARK)
                self.ax_fh.set_ylabel("Count",  color=DARK)
                self.ax_fh.set_title("Histogram", color=DARK)

        w.style_ax(self.ax_fh)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig_fh.tight_layout()
        self.canvas_fh.draw()
