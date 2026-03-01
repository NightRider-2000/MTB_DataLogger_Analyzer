import csv
import tkinter as tk
from tkinter import filedialog, messagebox

import widgets as w
from constants import BG, DARK, FIELD, ROW_ALT, CAL_FIELDS, HIST_COLORS


class CalibrationMixin:

    def _auto_populate_calibrations(self):
        numeric_cols = list(self.df.select_dtypes(include="number").columns)
        self.saved_calibrations = [
            {
                "signal":          col,
                "raw_min":         self.df[col].min(),
                "raw_max":         self.df[col].max(),
                "cal_min":         float("nan"),
                "cal_max":         float("nan"),
                "bias":            0.0,
                "new_signal_name": f"{col}_cal",
                "cal_result_min":  float("nan"),
                "cal_result_max":  float("nan"),
            }
            for col in numeric_cols
        ]
        self._refresh_cal_treeview()

    def _sync_form_to_table(self, event=None):
        col = self.cal_signal_var.get()
        if not col:
            return
        for cal in self.saved_calibrations:
            if cal["signal"] == col:
                cal["raw_min"]         = self.raw_min_entry.get()
                cal["raw_max"]         = self.raw_max_entry.get()
                cal["cal_min"]         = self.cal_min_entry.get()
                cal["cal_max"]         = self.cal_max_entry.get()
                cal["bias"]            = self.bias_entry.get()
                cal["new_signal_name"] = self.new_signal_entry.get()
                try:
                    raw_min, raw_max, cal_min, cal_max = self._read_cal_fields()
                    bias = float(self.bias_entry.get()) if self.bias_entry.get().strip() else 0.0
                    if raw_max != raw_min and self.df is not None:
                        a = (cal_max - cal_min) / (raw_max - raw_min)
                        b = cal_min - a * raw_min
                        result = a * self.df[col] + b - bias
                        cal["cal_result_min"] = round(result.min(), 6)
                        cal["cal_result_max"] = round(result.max(), 6)
                    else:
                        cal["cal_result_min"] = float("nan")
                        cal["cal_result_max"] = float("nan")
                except ValueError:
                    cal["cal_result_min"] = float("nan")
                    cal["cal_result_max"] = float("nan")
                break
        self._refresh_cal_treeview()
        self._update_cal_plots(autofill=False)

    def _read_cal_fields(self):
        """Return (raw_min, raw_max, cal_min, cal_max) or raise ValueError."""
        return (
            float(self.raw_min_entry.get()),
            float(self.raw_max_entry.get()),
            float(self.cal_min_entry.get()),
            float(self.cal_max_entry.get()),
        )

    def apply_calibration(self):
        if self.df is None:
            return
        col = self.cal_signal_var.get()
        if not col:
            return
        try:
            raw_min, raw_max, cal_min, cal_max = self._read_cal_fields()
        except ValueError:
            messagebox.showerror("Invalid Input", "Calibration fields must be numeric.")
            return
        if raw_max == raw_min:
            messagebox.showerror("Invalid Range", "Raw min and max must differ.")
            return

        a        = (cal_max - cal_min) / (raw_max - raw_min)
        b        = cal_min - a * raw_min
        new_name = self.new_signal_entry.get().strip() or col
        self.calibrated_df[new_name] = a * self.df[col] + b
        self.df[new_name]            = self.calibrated_df[new_name]
        self._refresh_signal_lists()
        self._update_cal_plots(autofill=False)

    def _update_cal_plots(self, event=None, autofill=True):
        col = self.cal_signal_var.get()
        if not col or self.df is None:
            return

        if autofill:
            self.raw_min_entry.delete(0, tk.END)
            self.raw_min_entry.insert(0, f"{self.df[col].min():.6g}")
            self.raw_max_entry.delete(0, tk.END)
            self.raw_max_entry.insert(0, f"{self.df[col].max():.6g}")
            self.new_signal_entry.delete(0, tk.END)
            self.new_signal_entry.insert(0, f"{col}_cal")

        # Raw panel
        self.ax_raw_cal.clear()
        self.ax_raw_cal.set_facecolor(BG)
        w.insert_gap_nans(self.df[col]).plot(ax=self.ax_raw_cal)
        self.ax_raw_cal.set_title("Raw", color=DARK)
        self.ax_raw_cal.set_ylabel(col, color=DARK)
        w.style_ax(self.ax_raw_cal)

        # Compute calibrated series once for reuse in both panels below
        new_name = self.new_signal_entry.get().strip() or col
        calibrated = None
        try:
            raw_min, raw_max, cal_min, cal_max = self._read_cal_fields()
            bias = float(self.bias_entry.get()) if self.bias_entry.get().strip() else 0.0
            if raw_max != raw_min:
                a = (cal_max - cal_min) / (raw_max - raw_min)
                b = cal_min - a * raw_min
                calibrated = a * self.df[col] + b - bias
        except ValueError:
            pass

        # Calibrated time series panel
        self.ax_cal.clear()
        self.ax_cal.set_facecolor(BG)
        w.insert_gap_nans(calibrated if calibrated is not None else self.df[col]).plot(ax=self.ax_cal)
        self.ax_cal.set_title("Calibrated", color=DARK)
        self.ax_cal.set_ylabel(new_name, color=DARK)
        w.style_ax(self.ax_cal)

        # Calibrated histogram panel
        self.ax_hist_cal.clear()
        self.ax_hist_cal.set_facecolor(BG)
        if calibrated is not None:
            data = calibrated.dropna()
            self.ax_hist_cal.hist(data, bins=40, alpha=0.7, color=HIST_COLORS[0])
        self.ax_hist_cal.set_title("Calibrated Histogram", color=DARK)
        self.ax_hist_cal.set_xlabel(new_name, color=DARK)
        self.ax_hist_cal.set_ylabel("Count", color=DARK)
        w.style_ax(self.ax_hist_cal)

        self.fig_cal.tight_layout()
        self.canvas_cal.draw()

    def save_current_calibration(self):
        col = self.cal_signal_var.get()
        if not col:
            messagebox.showwarning("No Signal", "Select a signal before saving.")
            return
        try:
            raw_min, raw_max, cal_min, cal_max = self._read_cal_fields()
        except ValueError:
            messagebox.showerror("Invalid Input", "All calibration fields must be numeric.")
            return

        entry = {"signal": col, "raw_min": raw_min, "raw_max": raw_max,
                 "cal_min": cal_min, "cal_max": cal_max}
        for i, existing in enumerate(self.saved_calibrations):
            if existing["signal"] == col:
                self.saved_calibrations[i] = entry
                self._refresh_cal_treeview()
                return
        self.saved_calibrations.append(entry)
        self._refresh_cal_treeview()

    def delete_selected_calibration(self):
        selected = self.cal_tree.selection()
        if not selected:
            return
        to_remove = {self.cal_tree.item(iid, "values")[0] for iid in selected}
        self.saved_calibrations = [c for c in self.saved_calibrations
                                   if c["signal"] not in to_remove]
        self._refresh_cal_treeview()

    def on_cal_tree_select(self, event):
        selected = self.cal_tree.selection()
        if not selected:
            return
        signal, raw_min, raw_max, cal_min, cal_max, bias, new_signal_name, *_ = self.cal_tree.item(selected[0], "values")
        if signal in self.cal_signal_combo["values"]:
            self.cal_signal_var.set(signal)
        for widget, val in [
            (self.raw_min_entry,    raw_min),
            (self.raw_max_entry,    raw_max),
            (self.cal_min_entry,    cal_min),
            (self.cal_max_entry,    cal_max),
            (self.bias_entry,       bias),
            (self.new_signal_entry, new_signal_name),
        ]:
            widget.delete(0, tk.END)
            widget.insert(0, val)
        self._update_cal_plots(autofill=False)

    def load_cal_file(self):
        path = filedialog.askopenfilename(
            title="Load Calibration CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, newline="") as f:
            self.saved_calibrations = [
                {k: (float(row[k]) if k != "signal" else row[k]) for k in CAL_FIELDS}
                for row in csv.DictReader(f)
            ]
        self.cal_file_path = path
        self._refresh_cal_treeview()

    def save_cal_file(self):
        if not self.saved_calibrations:
            messagebox.showinfo("Nothing to Save", "No calibrations to save.")
            return
        if self.cal_file_path is None:
            path = filedialog.asksaveasfilename(
                title="Save Calibration CSV",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
            if not path:
                return
            self.cal_file_path = path
        with open(self.cal_file_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(CAL_FIELDS))
            writer.writeheader()
            writer.writerows(self.saved_calibrations)

    def _refresh_cal_treeview(self):
        self.cal_tree.delete(*self.cal_tree.get_children())
        self.cal_tree.tag_configure("even", background=FIELD,   foreground=DARK)
        self.cal_tree.tag_configure("odd",  background=ROW_ALT, foreground=DARK)
        for i, cal in enumerate(self.saved_calibrations):
            self.cal_tree.insert("", tk.END,
                                 tags=("even" if i % 2 == 0 else "odd",),
                                 values=tuple(cal[k] for k in CAL_FIELDS))
