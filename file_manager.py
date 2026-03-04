import glob
import os
import tkinter as tk
from tkinter import filedialog, messagebox

import pandas as pd


class FileManagerMixin:

    def _populate_file_list(self):
        files = sorted(
            glob.glob(os.path.join(self._source_dir, "*.TXT")) +
            glob.glob(os.path.join(self._source_dir, "*.txt")),
            key=lambda f: os.path.basename(f).lower(),
        )
        self._download_paths = files
        self.file_listbox.delete(0, tk.END)
        for f in files:
            self.file_listbox.insert(tk.END, os.path.basename(f))

    def change_source_dir(self):
        directory = filedialog.askdirectory(title="Select Source Directory")
        if directory:
            self._source_dir = directory
            self._populate_file_list()

    def delete_selected_file(self):
        sel = self.file_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a file to delete.")
            return
        path = self._download_paths[sel[0]]
        if messagebox.askyesno("Confirm Delete",
                               f"Permanently delete '{os.path.basename(path)}'?\n\nThis cannot be undone."):
            os.remove(path)
            self._populate_file_list()

    def on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if sel:
            self._load_from_paths([self._download_paths[i] for i in sel])

    def _load_from_paths(self, file_paths):
        frames = []
        for file_path in file_paths:
            try:
                raw = pd.read_csv(file_path, on_bad_lines="skip")
            except Exception as e:
                messagebox.showerror("Load Error", f"Could not read file:\n{e}")
                return
            time_col = "rtcTime"
            if time_col in raw.columns:
                raw[time_col] = pd.to_datetime(raw[time_col], format="mixed", errors="coerce")
                raw = raw.set_index(time_col).sort_index()
            frames.append(raw)

        if len(frames) > 1:
            combined = pd.concat(frames)
            if all(isinstance(f.index, pd.DatetimeIndex) for f in frames):
                combined = combined.sort_index()
        else:
            combined = frames[0]
        self.df = combined
        self.calibrated_df = self.df.copy()

        self._refresh_signal_lists()
        numeric_cols = list(self.df.select_dtypes(include="number").columns)
        if numeric_cols:
            self.cal_signal_combo.current(0)
            self.signal_listbox.selection_set(0)
            first = [numeric_cols[0]]
        else:
            first = []
        self.plot_signals(first)
        self.plot_histogram(first)
        self._update_cal_plots()
        self._auto_populate_calibrations()
        self._apply_all_calibrations()

    def _refresh_signal_lists(self):
        numeric_cols = list(self.df.select_dtypes(include="number").columns)
        self.signal_listbox.delete(0, tk.END)
        for c in numeric_cols:
            self.signal_listbox.insert(tk.END, c)
        self.cal_signal_combo["values"] = numeric_cols
