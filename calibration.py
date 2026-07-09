import csv
import tkinter as tk
import warnings
from tkinter import filedialog, messagebox

import widgets as w
from constants import BG, DARK, FIELD, ROW_ALT, CAL_FIELDS, HIST_BAR_COLOR, GRID


class CalibrationMixin:

    def _auto_populate_calibrations(self):
        if self.cal_file_path is not None:
            return
        numeric_cols = list(self.df.select_dtypes(include="number").columns)
        self.saved_calibrations = [
            {
                "Signal":          col,
                "Calibrated_Name": f"{col}_cal",
                "Raw_Sig_Min":     self.df[col].min(),
                "Raw_Sig_Max":     self.df[col].max(),
                "Value_at_Min":    float("nan"),
                "Value_at_Max":    float("nan"),
                "Bias":            0.0,
                "Calibrated_Min":  float("nan"),
                "Calibrated_Max":  float("nan"),
            }
            for col in numeric_cols
        ]
        self._refresh_cal_treeview()

    # ── Header-config import (fork/shock calibration from the CSV #CFG block) ──
    # Each spec: (raw signal, extended-volt key, compressed-volt key, travel key).
    # The Honeywell suspension sensors read high volts fully extended (0 mm) and
    # low volts fully compressed (= sensor travel), so the calibration line is
    #   compressed_volts → travel_mm   and   extended_volts → 0 mm.
    _HEADER_SUSP_CAL = [
        ("analog1_v", "fork_v_extended",  "fork_v_compressed",  "fork_travel_mm"),
        ("analog2_v", "shock_v_extended", "shock_v_compressed", "shock_travel_mm"),
    ]

    def _recompute_calibrated_range(self, cal):
        """Refresh a row's Calibrated_Min/Max display from its raw/value points."""
        try:
            raw_min, raw_max = float(cal["Raw_Sig_Min"]), float(cal["Raw_Sig_Max"])
            val_min, val_max = float(cal["Value_at_Min"]), float(cal["Value_at_Max"])
            bias = float(cal["Bias"]) if str(cal["Bias"]).strip() else 0.0
            if (raw_max != raw_min and self.df is not None
                    and cal["Signal"] in self.df.columns):
                a = (val_max - val_min) / (raw_max - raw_min)
                b = val_min - a * raw_min
                result = a * self.df[cal["Signal"]] + b - bias
                cal["Calibrated_Min"] = round(float(result.min()), 6)
                cal["Calibrated_Max"] = round(float(result.max()), 6)
            else:
                cal["Calibrated_Min"] = float("nan")
                cal["Calibrated_Max"] = float("nan")
        except (ValueError, TypeError):
            cal["Calibrated_Min"] = float("nan")
            cal["Calibrated_Max"] = float("nan")

    def _apply_log_config_to_calibrations(self, cfg, progress_cb=None):
        """Update the fork/shock calibration rows in place from a parsed CSV
        ``#CFG`` header map. Returns the list of updated Calibrated_Names."""
        updated = []
        for signal, k_ext, k_comp, k_travel in self._HEADER_SUSP_CAL:
            try:
                v_ext  = float(cfg[k_ext])
                v_comp = float(cfg[k_comp])
                travel = float(cfg[k_travel])
            except (KeyError, ValueError, TypeError):
                continue
            if v_ext == v_comp:          # degenerate — can't form a line
                continue
            cal = next((c for c in self.saved_calibrations
                        if c["Signal"] == signal), None)
            if cal is None:
                continue
            cal["Raw_Sig_Min"]  = v_comp    # low volts  = fully compressed
            cal["Raw_Sig_Max"]  = v_ext     # high volts = fully extended
            cal["Value_at_Min"] = travel    # → sensor full travel (mm)
            cal["Value_at_Max"] = 0.0       # → 0 mm (extended)
            self._recompute_calibrated_range(cal)
            updated.append(cal["Calibrated_Name"])
        if updated:
            self._refresh_cal_treeview(progress_cb=progress_cb)
        return updated

    def _commit_form_to_table(self):
        """Write the current form fields into saved_calibrations for the
        signal selected in "Signal to calibrate". Does NOT recompute
        cal_result_df or redraw anything — editing the form alone has no
        effect; call apply_calibration_updates() (the "Apply Updates"
        button) to make edits take effect."""
        col = self.cal_signal_var.get()
        if not col:
            return
        for cal in self.saved_calibrations:
            if cal["Signal"] == col:
                cal["Raw_Sig_Min"]     = self.raw_min_entry.get()
                cal["Raw_Sig_Max"]     = self.raw_max_entry.get()
                cal["Value_at_Min"]    = self.cal_min_entry.get()
                cal["Value_at_Max"]    = self.cal_max_entry.get()
                cal["Bias"]            = self.bias_entry.get()
                cal["Calibrated_Name"] = self.new_signal_entry.get()
                self._recompute_calibrated_range(cal)
                return

    def apply_calibration_updates(self):
        """"Apply Updates" button — the only way form edits take effect.
        Commits the form into saved_calibrations, recomputes cal_result_df,
        and refreshes every tab (including this tab's own preview)."""
        self._commit_form_to_table()
        dialog = w.ProgressDialog(self, "Applying calibration updates…")
        try:
            self._apply_all_calibrations(progress_cb=dialog.step)
        finally:
            dialog.close()
        self._update_cal_plots(autofill=False)

    # ── Auto-calibrate fork/shock: zero the calibrated minimum ────────────────
    # Sets Bias so the calibrated position's minimum over the WHOLE loaded ride
    # is exactly 0 — e.g. zeroes a suspension channel to its most-extended
    # point actually observed in the data, correcting small offset/mounting
    # error without touching the Raw/Value calibration points.

    def _auto_calibrate_zero_min(self, raw_signal, label):
        if self.df is None or raw_signal not in self.df.columns:
            messagebox.showwarning("No Data", "Load ride data first.")
            return
        cal = next((c for c in self.saved_calibrations if c["Signal"] == raw_signal), None)
        if cal is None:
            messagebox.showwarning("No Calibration",
                                   f"No calibration row found for {label} ({raw_signal}).")
            return
        try:
            raw_min = float(cal["Raw_Sig_Min"])
            raw_max = float(cal["Raw_Sig_Max"])
            val_min = float(cal["Value_at_Min"])
            val_max = float(cal["Value_at_Max"])
        except (ValueError, TypeError):
            messagebox.showerror("Invalid Calibration",
                                 f"{label}: Raw/Value fields must be numeric.")
            return
        if raw_max == raw_min:
            messagebox.showerror("Invalid Range", f"{label}: Raw min and max must differ.")
            return

        a = (val_max - val_min) / (raw_max - raw_min)
        b = val_min - a * raw_min
        unbiased = a * self.df[raw_signal] + b   # bias-free calibrated series
        cal["Bias"] = round(float(unbiased.min()), 6)

        if self.cal_signal_var.get() == raw_signal:
            self.bias_entry.delete(0, tk.END)
            self.bias_entry.insert(0, str(cal["Bias"]))

        dialog = w.ProgressDialog(self, f"Auto-calibrating {label}…")
        try:
            self._apply_all_calibrations(progress_cb=dialog.step)
        finally:
            dialog.close()
        self._update_cal_plots(autofill=False)

    def auto_calibrate_fork(self):
        self._auto_calibrate_zero_min("analog1_v", "Fork")

    def auto_calibrate_shock(self):
        self._auto_calibrate_zero_min("analog2_v", "Shock")

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
            self.new_signal_entry.set("")

        # Raw panel
        self.ax_raw_cal.clear()
        self.ax_raw_cal.set_facecolor(BG)
        w.plot_time_series_smart(self.ax_raw_cal, self.df[col])
        # Always pin the x-axis to the ride's real time range — an all-NaN
        # signal otherwise leaves matplotlib's default 0..1 axis in place,
        # which renders as garbled dates on a datetime axis.
        self.ax_raw_cal.set_xlim(self.df.index.min(), self.df.index.max())
        if self.df[col].isna().all():
            self.ax_raw_cal.text(0.5, 0.5, "No Data Available",
                                 transform=self.ax_raw_cal.transAxes,
                                 ha="center", va="center", color=DARK, fontsize=14)
        self.ax_raw_cal.set_title("Raw", color=DARK)
        self.ax_raw_cal.set_ylabel(col, color=DARK)
        w.style_ax(self.ax_raw_cal)
        w.format_time_axis(self.ax_raw_cal)

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

        # Override with edge-detected result if available in cal_result_df
        if (self.cal_result_df is not None
                and new_name in self.cal_result_df.columns):
            calibrated = self.cal_result_df[new_name]

        # Calibrated time series panel
        self.ax_cal.clear()
        self.ax_cal.set_facecolor(BG)
        _cal_series = calibrated if calibrated is not None else self.df[col]
        w.plot_time_series_smart(self.ax_cal, _cal_series)
        # Same index as self.df (cal_result_df / the affine transform both
        # preserve it), so the ride's real time range applies here too.
        self.ax_cal.set_xlim(self.df.index.min(), self.df.index.max())
        if _cal_series.isna().all():
            self.ax_cal.text(0.5, 0.5, "No Data Available",
                             transform=self.ax_cal.transAxes,
                             ha="center", va="center", color=DARK, fontsize=14)
        self.ax_cal.set_title("Calibrated", color=DARK)
        self.ax_cal.set_ylabel(new_name, color=DARK)
        w.style_ax(self.ax_cal)
        w.format_time_axis(self.ax_cal)

        # Calibrated histogram panel
        self.ax_hist_cal.clear()
        self.ax_hist_cal.set_facecolor(BG)
        data = calibrated.dropna() if calibrated is not None else calibrated
        if data is not None and not data.empty:
            color = HIST_BAR_COLOR
            mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
            self.ax_hist_cal.hist(data, bins=200, alpha=0.45, color=color)
            self.ax_hist_cal.axvline(mean, color=color, linestyle="--", linewidth=1.5)
            self.ax_hist_cal.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
            self.ax_hist_cal.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist_cal.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist_cal.axvspan(mean - std, mean + std, alpha=0.12, color=color)
            stats_text = f"{new_name}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}"
            self.ax_hist_cal.text(
                0.97, 0.97, stats_text,
                transform=self.ax_hist_cal.transAxes, fontsize=10,
                verticalalignment="top", horizontalalignment="right", color=DARK,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9),
            )
        else:
            self.ax_hist_cal.text(0.5, 0.5, "No Data Available",
                                  transform=self.ax_hist_cal.transAxes,
                                  ha="center", va="center", color=DARK, fontsize=14)
        self.ax_hist_cal.set_title("Calibrated Histogram", color=DARK)
        self.ax_hist_cal.set_xlabel(new_name, color=DARK)
        self.ax_hist_cal.set_ylabel("Count", color=DARK)
        w.style_ax(self.ax_hist_cal)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
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

        entry = {"Signal": col, "Raw_Sig_Min": raw_min, "Raw_Sig_Max": raw_max,
                 "Value_at_Min": cal_min, "Value_at_Max": cal_max}
        for i, existing in enumerate(self.saved_calibrations):
            if existing["Signal"] == col:
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
                                   if c["Signal"] not in to_remove]
        self._refresh_cal_treeview()

    def on_cal_tree_select(self, event):
        selected = self.cal_tree.selection()
        if not selected:
            return
        signal, calibrated_name, raw_sig_min, raw_sig_max, value_at_min, value_at_max, bias, *_ = \
            self.cal_tree.item(selected[0], "values")
        if signal in self.cal_signal_combo["values"]:
            self.cal_signal_var.set(signal)
        for widget, val in [
            (self.raw_min_entry, raw_sig_min),
            (self.raw_max_entry, raw_sig_max),
            (self.cal_min_entry, value_at_min),
            (self.cal_max_entry, value_at_max),
            (self.bias_entry,    bias),
        ]:
            widget.delete(0, tk.END)
            widget.insert(0, val)
        self.new_signal_entry.set(calibrated_name)
        self._update_cal_plots(autofill=False)

    def _load_cal_from_path(self, path):
        _float_defaults = {
            "Raw_Sig_Min":    float("nan"), "Raw_Sig_Max":    float("nan"),
            "Value_at_Min":   float("nan"), "Value_at_Max":   float("nan"),
            "Bias":           0.0,
            "Calibrated_Min": float("nan"), "Calibrated_Max": float("nan"),
        }
        rows = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                entry = {"Signal":          row.get("Signal", "").strip(),
                         "Calibrated_Name": row.get("Calibrated_Name", "").strip()}
                for k, default in _float_defaults.items():
                    raw_val = row.get(k, "")
                    try:
                        entry[k] = float(raw_val) if raw_val.strip() else default
                    except (ValueError, AttributeError):
                        entry[k] = default
                rows.append(entry)
        self.saved_calibrations = rows
        self.cal_file_path = path
        self._refresh_cal_treeview()

    def load_cal_file(self):
        path = filedialog.askopenfilename(
            title="Load Calibration CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        self._load_cal_from_path(path)

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

    def _derive_speed(self, cal_name, trig_var_name, circ_var_name, mode):
        """Convert a firmware frequency channel (spdN_hz) into a wheel speed
        (mph) or crank speed (rpm). The calibration row whose Calibrated_Name
        == cal_name links the target name to its raw spdN_hz column."""
        cal = next((c for c in self.saved_calibrations
                    if c.get("Calibrated_Name", "").strip() == cal_name), None)
        if not cal or cal.get("Signal") not in self.df.columns or not hasattr(self, trig_var_name):
            return
        try:
            triggers_per_rev = max(1, int(float(getattr(self, trig_var_name).get())))
        except (ValueError, TypeError):
            return
        raw = self.df[cal["Signal"]].dropna()
        if len(raw) < 3:
            return
        # Pair-average 2 consecutive Hz readings, then despike IN THE PAIR-MEAN
        # DOMAIN — order matters. Measured stream structure (ride
        # 20260703_200146): the CRANK strictly alternates high/low (~2.6–2.9x
        # within-pair vs between-pair — the documented 5-pair geometry is real
        # there), while the WHEELS are only mildly unequal (0.7–1.4x). A median
        # applied to the raw crank stream would flatten the alternation
        # (median(L,H,L)=L) and bias cadence low, so all despiking runs on the
        # smooth pair-mean instead.
        #
        # Despike target: prox-sensor re-trigger chatter — an occasional extra
        # falling edge inside a target's passage that splits one normal gap in
        # two (isolated raw spike, ~4.5–5.5x on wheels / ~3–5x on crank;
        # verified: spike period + following period == exactly one normal
        # inter-target gap). Two stages, both required:
        #   1. Drop pair-means > 1.8x their local rolling median-31 (~2.1s of
        #      pedaling at the ride's ~67ms/pair spacing). A single chatter
        #      edge corrupts 2 consecutive pair-means, but DOUBLE chatter (two
        #      extra edges ~60 ms apart — observed) corrupts 5–6 in a row,
        #      which no small median can clip; dropping against a wide local
        #      reference handles runs of any length. Window was widened
        #      15→31 (2026-07-05, ride w/ improved sensor bracket/mount still
        #      showing a residual spike) — validated on the reference ride:
        #      residual "hot" (>1.5x a 101-sample reference) samples dropped
        #      32→19, and the two multi-sample plateau runs (length 6 and 9)
        #      that survived at window-15 are gone entirely at window-31.
        #      Window is capped there, NOT pushed wider: at ~67ms/pair-mean,
        #      31 samples already spans ~2.1s of ride time — wider risks the
        #      filter lagging behind a genuine fast cadence change (e.g. a
        #      sprint start) and rejecting real data as if it were chatter.
        #      NOTE: the mildest bursts (~1.5–1.7x true cadence) survive at
        #      ANY window width, because their own ratio sits genuinely below
        #      the 1.8x cutoff — that's not reference contamination, it's the
        #      threshold intentionally staying clear of genuine cadence
        #      variation. Only lowering the ratio would reach those, at the
        #      cost of false-positiving on real speed changes.
        #   2. Rolling median-5 polish for the residual remainder-gap wiggle
        #      (~1.25–1.45x samples that stage 1's threshold ignores).
        # Validated on the ride above: derived-speed samples >2x local median
        # 200/194/185 → 0/0/0 (front/rear/crank), medians preserved within 1%,
        # ~2% of wheel samples dropped (= the chatter population). Firmware
        # ≥ v79 also rejects wheel chatter at capture time (speed.cpp), but
        # this keeps older logs and the crank (excluded from the firmware
        # filter — its alternation overlaps the chatter ratio) clean too.
        # (Triggers/rev validated against GPS ground speed 2026-07-05: implied
        # ~12.6 targets/rev on the rear wheel — the ÷12 default is correct.)
        #
        # Sustained bursts (3-5 consecutive spurious raw captures, ~7% of the
        # crank's chatter events — rarer than the isolated/double case above)
        # can survive a single pass: stage 1's own local-median-15 reference
        # gets partly contaminated by the burst, so the ratio test can miss a
        # sample, and stage 2's median-5 can't out-vote a majority-corrupted
        # window. Re-running stages 1+2 a second time over the already-once-
        # cleaned pair-mean stream (NOT re-pairing from raw again) fixes this,
        # since its local reference is no longer contaminated by whatever the
        # first pass already removed. Capped at one extra pass — diminishing
        # returns past that.
        pair_hz = raw.rolling(2).mean().dropna()
        for _ in range(2):
            local   = pair_hz.rolling(31, center=True, min_periods=10).median()
            pair_hz = pair_hz[pair_hz <= 1.8 * local]
            pair_hz = pair_hz.rolling(5, center=True, min_periods=1).median()
        rev_per_s = pair_hz / triggers_per_rev
        if mode == "rpm":
            vals = rev_per_s * 60.0
        else:  # mph = in/rev · rev/s · 3600 s/hr ÷ 63360 in/mile
            try:
                circ_in = float(getattr(self, circ_var_name).get())
            except (AttributeError, ValueError, TypeError):
                return
            vals = rev_per_s * circ_in * 3600.0 / 63360.0
        # Hold each sparse reading until the next, up to ~0.5 s (rate from data).
        period = w.sample_period_s(self.df.index)
        limit  = int(round(0.5 / period)) if period else 20
        self.cal_result_df[cal_name] = vals.reindex(self.df.index).ffill(limit=limit)

    @staticmethod
    def _time_varying_lowpass_loop(sig, dt_arr, two_pi_fc, period_fallback):
        """Reference implementation (row-by-row): one-pole low-pass with a
        per-sample time constant derived from the row's actual dt (handles
        file-boundary gaps and duplicate timestamps). O(n) in pure Python —
        kept only as the exact-behavior fallback for the rare case where
        ``sig`` itself contains NaN (see _time_varying_lowpass)."""
        import numpy as np
        n = len(sig)
        out = np.empty(n)
        out[0] = sig[0]
        for i in range(1, n):
            dt_i = dt_arr[i] if np.isfinite(dt_arr[i]) and dt_arr[i] > 0 else (period_fallback or 1.0 / 240.0)
            a    = dt_i / (1.0 / two_pi_fc + dt_i)
            prev = out[i - 1] if np.isfinite(out[i - 1]) else sig[i]
            out[i] = a * sig[i] + (1.0 - a) * prev if np.isfinite(sig[i]) else prev
        return out

    @staticmethod
    def _time_varying_lowpass(sig, dt_arr, two_pi_fc, period_fallback, block=4096):
        """Vectorized equivalent of _time_varying_lowpass_loop for the common
        case where ``sig`` has no NaN (dense analog channels — this is the
        norm; sparse/NaN-filled channels like GPS never go through this path).
        Exact to float64 precision, not an approximation: the recursion
        y[i] = a[i]*sig[i] + (1-a[i])*y[i-1] has a closed form via a
        cumulative product, but a single global cumulative product underflows
        to 0 over long rides (the filter's ~0.3 Hz cutoff means old samples
        decay to ~0 within a few thousand rows anyway) — so it's computed in
        blocks, carrying the true running value forward as each block's
        initial condition. This is ~150x faster than the row-by-row loop for
        a 30-minute ride and was validated against it (incl. duplicate
        timestamps / multi-file gap boundaries) to ~1e-13 absolute error.
        Falls back to the loop if sig contains any NaN, preserving the loop's
        exact "hold last value" semantics for that rare/defensive case."""
        import numpy as np
        n = len(sig)
        if n == 0:
            return np.array([])
        if np.isnan(sig).any():
            return CalibrationMixin._time_varying_lowpass_loop(
                sig, dt_arr, two_pi_fc, period_fallback)

        dt = np.where(np.isfinite(dt_arr) & (dt_arr > 0), dt_arr,
                      (period_fallback or 1.0 / 240.0))
        a = dt / (1.0 / two_pi_fc + dt)
        b = 1.0 - a
        out = np.empty(n)
        out[0] = sig[0]
        prev = out[0]
        for start in range(1, n, block):
            end = min(start + block, n)
            ai, bi, xi = a[start:end], b[start:end], sig[start:end]
            p = np.cumprod(bi)                    # within-block decay factor
            s = np.cumsum(ai * xi / p)
            block_out = p * (prev + s)
            out[start:end] = block_out
            prev = block_out[-1]
        return out

    @staticmethod
    def _savgol_velocity(series, period, window=7, poly=6):
        """Velocity (units/s) as a Savitzky-Golay first derivative of position.
        Decided design (doc/suspension_daq_sampling_rate.pdf): suspension/wheel
        velocity is derived OFFLINE from the logged position, not on-device.
        Returns NaN where the source position is NaN; ``period`` (s) sets the
        derivative spacing and MUST come from the data, never hardcoded."""
        import numpy as np
        import pandas as pd
        from scipy.signal import savgol_filter
        vals = series.values.astype(float)
        n = len(vals)
        out = np.full(n, np.nan)
        finite = np.isfinite(vals)
        if not period or n < window or finite.sum() < window:
            return out
        filled = pd.Series(vals).interpolate(limit_direction="both").values
        vel = savgol_filter(filled, window_length=window, polyorder=poly,
                            deriv=1, delta=period)
        out[finite] = vel[finite]
        return out

    def _apply_all_calibrations(self, progress_cb=None):
        """Recompute cal_result_df from saved_calibrations and refresh every
        tab. ``progress_cb(label, frac)``, if given, is called at named
        checkpoints (frac in [0,1]) — wire it to widgets.ProgressDialog.step
        for a "please wait" window on this (the slowest operation in the app,
        run for every file load and every Apply Updates / Auto-Cal click)."""
        def _progress(label, frac):
            if progress_cb:
                progress_cb(label, frac)

        if self.df is None:
            return
        import math
        import pandas as pd
        _progress("Applying raw→calibrated transforms…", 0.0)
        cols = {}
        for cal in self.saved_calibrations:
            signal   = cal["Signal"]
            cal_name = cal.get("Calibrated_Name", "").strip() or f"{signal}_cal"
            if signal not in self.df.columns:
                continue
            try:
                raw_min = float(cal["Raw_Sig_Min"])
                raw_max = float(cal["Raw_Sig_Max"])
                val_min = float(cal["Value_at_Min"])
                val_max = float(cal["Value_at_Max"])
                bias    = float(cal["Bias"]) if str(cal["Bias"]).strip() else 0.0
            except (ValueError, TypeError):
                continue
            if any(math.isnan(v) for v in [raw_min, raw_max, val_min, val_max]):
                continue
            if raw_max == raw_min:
                continue
            a = (val_max - val_min) / (raw_max - raw_min)
            b = val_min - a * raw_min
            cols[cal_name] = a * self.df[signal] + b - bias
        self.cal_result_df = pd.DataFrame(cols, index=self.df.index)

        # GPS ground speed is logged in m/s (firmware gps.speed_mps). Always
        # express it in mph and suffix the column name to match.
        if "gps_spd" in self.cal_result_df.columns:
            _MPS_TO_MPH = 2.23694
            self.cal_result_df["gps_spd_mph"] = (
                self.cal_result_df["gps_spd"] * _MPS_TO_MPH)
            self.cal_result_df.drop(columns=["gps_spd"], inplace=True)

        # Rotate raw IMU body-frame signals → ISO 8855 vehicle frame
        # (X fwd, Y left, Z up). The LSM6DSV16X is installed with:
        #   +X_body = backward & 30° down
        #   +Y_body = down & 30° forward
        #   +Z_body = to the right
        # Expressing each body axis in the vehicle frame and stacking gives the
        # fixed rotation R (vehicle ← body); θ is the mounting pitch offset:
        #   fwd  = -cosθ·x + sinθ·y
        #   left = -z                    (vehicle +Y is left; +Z_body points right)
        #   up   = -sinθ·x - cosθ·y
        # Rest check (chip reads +g up): x≈-g·sinθ, y≈-g·cosθ, z≈0
        #   → aVert = +1g, aFwd = 0, aLat = 0.  TODO: validate signs vs real log.
        if "aX_g" in self.cal_result_df.columns and "aY_g" in self.cal_result_df.columns:
            import numpy as np
            try:
                _theta = np.radians(float(self.pitch_offset_var.get()))
            except (AttributeError, ValueError):
                _theta = np.radians(30.0)
            self._imu_theta_rad = _theta
            _cosT, _sinT = np.cos(_theta), np.sin(_theta)

            def _rotate(prefix, suffix, out_fwd, out_up, out_lat):
                # out_fwd ← fwd component, out_up ← up component, out_lat ← lateral.
                cols = [f"{prefix}{ax}{suffix}" for ax in ("X", "Y", "Z")]
                if cols[0] not in self.cal_result_df.columns or cols[1] not in self.cal_result_df.columns:
                    return
                vx = self.cal_result_df[cols[0]].values.astype(float)
                vy = self.cal_result_df[cols[1]].values.astype(float)
                vz = (self.cal_result_df[cols[2]].values.astype(float)
                      if cols[2] in self.cal_result_df.columns else np.zeros(len(vx)))
                self.cal_result_df[out_fwd] = -_cosT * vx + _sinT * vy
                self.cal_result_df[out_lat] = -vz
                self.cal_result_df[out_up]  = -_sinT * vx - _cosT * vy
                self.cal_result_df.drop(columns=[c for c in cols
                                                 if c in self.cal_result_df.columns], inplace=True)

            # accel: fwd/up/lat;  gyro: roll(=fwd axis)/yaw(=up axis)/pitch(=lat axis)
            _rotate("a", "_g",   "aFwd_g",    "aVert_g",  "aLat_g")
            _rotate("g", "_DPS", "gRoll_DPS", "gYaw_DPS", "gPitch_DPS")
            # (no magnetometer on the LSM6DSV16X — heading comes from the gyro)

        # ── Wheel / crank speed from the firmware's frequency channels ─────────
        # The Teensy logs spd1/2/3 already in Hz (FreqMeasureMulti), sparse —
        # a value only on the 240 Hz row where a trigger was captured, NaN
        # otherwise. The raw Hz alternates high/low because the triggers are in
        # unequally-spaced pairs, so we average 2 consecutive readings to get
        # one representative trigger frequency, then divide by triggers-per-rev
        # (wheel 12, crank 10) to get rev/s. (Firmware doc shorthand "×6 / ×5".)
        # TODO: validate the trigger/pair factor against a real motion log.
        _progress("Deriving wheel/crank speed…", 1 / 7)
        self._derive_speed("Crank_Spd_RPM",            "chain_ring_spokes_var", None,                  "rpm")
        self._derive_speed("Front_Horz_Wheel_Spd_mph", "front_spoke_count_var", "front_wheel_circ_var", "mph")
        self._derive_speed("Rear_Horz_Wheel_Spd_mph",  "rear_spoke_count_var",  "rear_wheel_circ_var",  "mph")

        # Rear wheel position via motion ratio lookup
        if (hasattr(self, "mr_tree")
                and "Shock_Pos_mm" in self.cal_result_df.columns):
            import numpy as np
            shock_lut, wheel_lut = [], []
            for iid in self.mr_tree.get_children():
                vals = self.mr_tree.item(iid, "values")
                try:
                    shock_lut.append(float(vals[0]))
                    wheel_lut.append(float(vals[1]))
                except (ValueError, IndexError):
                    pass
            if len(shock_lut) >= 2:
                self.cal_result_df["Rear_Wheel_Pos_mm"] = np.interp(
                    self.cal_result_df["Shock_Pos_mm"].values,
                    shock_lut, wheel_lut,
                )

        # Front wheel position from head tube angle and fork position
        if (hasattr(self, "head_tube_angle_var")
                and "Fork_Pos_mm" in self.cal_result_df.columns):
            import numpy as np
            try:
                angle_deg = float(self.head_tube_angle_var.get())
                self.cal_result_df["Front_Wheel_Pos_mm"] = (
                    np.sin(np.radians(angle_deg)) * self.cal_result_df["Fork_Pos_mm"]
                )
            except (ValueError, TypeError):
                pass

        # Normalized fork position percentage
        if (hasattr(self, "front_travel_var")
                and "Fork_Pos_mm" in self.cal_result_df.columns):
            try:
                front_max = float(self.front_travel_var.get())
                if front_max:
                    self.cal_result_df["Fork_Pos_Perc"] = (
                        self.cal_result_df["Fork_Pos_mm"] / front_max * 100
                    )
            except (ValueError, TypeError):
                pass

        # Normalized shock position percentage
        if (hasattr(self, "rear_travel_var")
                and "Shock_Pos_mm" in self.cal_result_df.columns):
            try:
                rear_max = float(self.rear_travel_var.get())
                if rear_max:
                    self.cal_result_df["Shock_Pos_Perc"] = (
                        self.cal_result_df["Shock_Pos_mm"] / rear_max * 100
                    )
            except (ValueError, TypeError):
                pass

        # Front wheel position percentage
        if (hasattr(self, "front_susp_travel_var")
                and "Front_Wheel_Pos_mm" in self.cal_result_df.columns):
            try:
                front_susp_max = float(self.front_susp_travel_var.get())
                if front_susp_max:
                    self.cal_result_df["Front_Wheel_Pos_Perc"] = (
                        self.cal_result_df["Front_Wheel_Pos_mm"] / front_susp_max * 100
                    )
            except (ValueError, TypeError):
                pass

        # Rear wheel position percentage
        if (hasattr(self, "rear_susp_travel_var")
                and "Rear_Wheel_Pos_mm" in self.cal_result_df.columns):
            try:
                rear_susp_max = float(self.rear_susp_travel_var.get())
                if rear_susp_max:
                    self.cal_result_df["Rear_Wheel_Pos_Perc"] = (
                        self.cal_result_df["Rear_Wheel_Pos_mm"] / rear_susp_max * 100
                    )
            except (ValueError, TypeError):
                pass

        _progress("Computing wheel position…", 2 / 7)

        # Wheel vertical speed (mm/s) — Savitzky-Golay derivative of position.
        _period = w.sample_period_s(self.cal_result_df.index)
        for _pos, _spd in [
            ("Front_Wheel_Pos_mm", "Front_Vert_Wheel_Spd_mmps"),
            ("Rear_Wheel_Pos_mm",  "Rear_Vert_Wheel_Spd_mmps"),
        ]:
            if _pos in self.cal_result_df.columns:
                self.cal_result_df[_spd] = self._savgol_velocity(
                    self.cal_result_df[_pos], _period)

        # Wheel-in-air flags
        if "Front_Wheel_Pos_Perc" in self.cal_result_df.columns:
            self.cal_result_df["Front_Wheel_Air"] = (
                self.cal_result_df["Front_Wheel_Pos_Perc"] <= 9
            ).astype(int)
        if "Rear_Wheel_Pos_Perc" in self.cal_result_df.columns:
            self.cal_result_df["Rear_Wheel_Air"] = (
                self.cal_result_df["Rear_Wheel_Pos_Perc"] <= 9
            ).astype(int)

        _progress("Computing suspension velocity + dynamic sag…", 3 / 7)

        # Dynamic sag: 0.3 Hz low-pass of Wheel_Pos_Perc, mean-centred
        #   result = filtered - mean(filtered)  [% points]
        _TWO_PI_FC = 2.0 * np.pi * 0.3   # 0.3 Hz cutoff
        _period_sag = w.sample_period_s(self.cal_result_df.index)
        _dt_arr = self.cal_result_df.index.to_series().diff().dt.total_seconds().values
        for _src, _dst in [
            ("Front_Wheel_Pos_Perc", "Front_Dynamic_Sag_Perc"),
            ("Rear_Wheel_Pos_Perc",  "Rear_Dynamic_Sag_Perc"),
        ]:
            if _src in self.cal_result_df.columns:
                _sig = self.cal_result_df[_src].values.astype(float)
                _out = self._time_varying_lowpass(_sig, _dt_arr, _TWO_PI_FC, _period_sag)
                self.cal_result_df[_dst] = _out - np.nanmean(_out)

        _progress("Selecting gear / computing IMU attitude…", 4 / 7)

        # Gear selection: nearest cassette sprocket from crank/wheel RPM ratio
        if ("Crank_Spd_RPM" in self.cal_result_df.columns
                and "Rear_Horz_Wheel_Spd_mph" in self.cal_result_df.columns
                and hasattr(self, "cassette_tree")
                and hasattr(self, "chain_ring_teeth_var")
                and hasattr(self, "rear_wheel_circ_var")):
            try:
                _cr_teeth  = float(self.chain_ring_teeth_var.get())
                _circ_in   = float(self.rear_wheel_circ_var.get())
                # Read cassette: list of (gear_number, teeth) sorted by gear number
                _cass_rows = [(int(self.cassette_tree.set(iid, "Gear")),
                               float(self.cassette_tree.set(iid, "Teeth")))
                              for iid in self.cassette_tree.get_children()]
                _cass_rows.sort(key=lambda r: r[0])
                _gear_nums  = np.array([r[0] for r in _cass_rows], dtype=float)
                _cass_teeth = np.array([r[1] for r in _cass_rows], dtype=float)

                _crank_rpm = self.cal_result_df["Crank_Spd_RPM"].values.astype(float)
                _speed_mph = self.cal_result_df["Rear_Horz_Wheel_Spd_mph"].values.astype(float)
                # wheel RPM = speed_mph * 5280 * 12 / (circ_in * 60)
                _wheel_rpm = _speed_mph * 1056.0 / _circ_in

                # apparent sprocket teeth = chainring_teeth * crank_rpm / wheel_rpm
                with np.errstate(divide="ignore", invalid="ignore"):
                    _apparent = np.where(
                        (_wheel_rpm > 0) & (_crank_rpm > 0),
                        _cr_teeth * _crank_rpm / _wheel_rpm,
                        np.nan)

                # For each sample find nearest cassette gear
                _gear = np.full(len(_apparent), np.nan)
                _valid = np.isfinite(_apparent)
                if _valid.any():
                    _diffs = np.abs(_apparent[_valid, None] - _cass_teeth[None, :])
                    _gear[_valid] = _gear_nums[_diffs.argmin(axis=1)]

                self.cal_result_df["Gear_Selected"] = _gear
            except Exception as e:
                print(f"Gear selection calc error: {e}")

        # IMU attitude — Pitch / Roll / Yaw (deg) from the SFLP quaternion.
        # The LSM6DSV16X runs 6-axis sensor fusion on-chip and logs the "game
        # rotation vector" quaternion vector part (quat_x/y/z, body frame); the
        # scalar qw is reconstructed here from the unit-norm constraint. We
        # rotate the body-frame orientation into the vehicle frame using the
        # fixed mount rotation R (same install axes as the accel/gyro block),
        # zero out the rest pose, and read Euler angles. Quat NaN → NaN out.
        # TODO: validate Euler signs/order against a real log once available.
        if all(s in self.df.columns for s in ("quat_x", "quat_y", "quat_z")):
            import numpy as np
            try:
                from scipy.spatial.transform import Rotation as _Rot

                _qx = self.df["quat_x"].values.astype(float)
                _qy = self.df["quat_y"].values.astype(float)
                _qz = self.df["quat_z"].values.astype(float)
                _qw = np.sqrt(np.clip(1.0 - (_qx**2 + _qy**2 + _qz**2), 0.0, 1.0))

                n = len(_qx)
                pitch = np.full(n, np.nan)
                roll  = np.full(n, np.nan)
                yaw   = np.full(n, np.nan)
                valid = np.isfinite(_qx) & np.isfinite(_qy) & np.isfinite(_qz)

                if valid.any():
                    # Fixed body→vehicle mount rotation (X back/down-θ, Y down/fwd-θ,
                    # Z right) → ISO 8855 (X fwd, Y left, Z up).
                    _theta = getattr(self, "_imu_theta_rad", np.radians(30.0))
                    _c, _s = np.cos(_theta), np.sin(_theta)
                    _R_vb = _Rot.from_matrix([[-_c,  _s, 0.0],
                                              [0.0, 0.0, -1.0],
                                              [-_s, -_c, 0.0]])
                    # SFLP quaternion = body→world (gravity-aligned, yaw arbitrary)
                    _R_wb = _Rot.from_quat(np.column_stack([_qx[valid], _qy[valid],
                                                            _qz[valid], _qw[valid]]))
                    _R_wv = _R_wb * _R_vb.inv()          # world ← vehicle
                    _R_ref = _R_wv[0]                    # zero the rest pose
                    _R_rel = _R_ref.inv() * _R_wv
                    _eul = _R_rel.as_euler("ZYX", degrees=True)   # yaw, pitch, roll
                    yaw[valid]   = _eul[:, 0]
                    pitch[valid] = _eul[:, 1]
                    roll[valid]  = _eul[:, 2]

                self.cal_result_df["Pitch_deg"] = pitch
                self.cal_result_df["Roll_deg"]  = roll
                self.cal_result_df["Yaw_deg"]   = yaw
            except Exception as e:
                print(f"Attitude (quaternion) calc error: {e}")

        _progress("Finalizing calibration table…", 5 / 7)

        # Update Calibrated_Min / Calibrated_Max in saved_calibrations
        for cal in self.saved_calibrations:
            cal_name = cal.get("Calibrated_Name", "").strip() or f"{cal['Signal']}_cal"
            if cal_name in self.cal_result_df.columns:
                series = self.cal_result_df[cal_name].dropna()
                if not series.empty:
                    cal["Calibrated_Min"] = round(series.min(), 6)
                    cal["Calibrated_Max"] = round(series.max(), 6)
                else:
                    cal["Calibrated_Min"] = float("nan")
                    cal["Calibrated_Max"] = float("nan")

        # Cache the unfiltered result and clear any active time filter — the
        # GPS tab's time-range filter slices this cached frame (see _apply_time_filter).
        self._cal_full = self.cal_result_df
        self._time_filter = None
        if hasattr(self, "_gps_reset_markers"):
            self._gps_reset_markers()
        _progress("Refreshing all tabs…", 6 / 7)
        # Scale the redraw sub-steps' own 0..1 fraction into this function's
        # remaining [6/7, 1) range so the bar keeps advancing monotonically
        # instead of jumping back to 0 when the redraw phase starts.
        _redraw_cb = ((lambda label, frac: progress_cb(label, 6 / 7 + frac / 7))
                      if progress_cb else None)
        self._refresh_all_analysis_tabs(progress_cb=_redraw_cb)
        _progress("Done", 1.0)

    def _refresh_all_analysis_tabs(self, progress_cb=None):
        """Redraw every analysis tab from the current self.cal_result_df view."""
        _steps = [
            ("Free Scatter",   self._refresh_free_plot_signals),
            ("Free Histogram", self._refresh_free_histogram_signals),
            ("Time Series",    self._refresh_ts_signals),
            ("Sag",            self._update_sag_plots),
            ("Susp Speed",     self._update_susp_speed_plots),
            ("Frequency",      self._update_frequency_plot),
            ("IMU",            self._update_imu_plots),
        ]
        if hasattr(self, "_update_gps_plots"):
            _steps.append(("GPS", self._update_gps_plots))
        for i, (label, fn) in enumerate(_steps):
            if progress_cb:
                progress_cb(f"Redrawing {label} tab…", i / len(_steps))
            fn()
        self._refresh_cal_treeview_display()

    def _refresh_cal_treeview_display(self):
        """Redraw the treeview from saved_calibrations without re-running calibrations."""
        self.cal_tree.delete(*self.cal_tree.get_children())
        self.cal_tree.tag_configure("even", background=FIELD,   foreground=DARK)
        self.cal_tree.tag_configure("odd",  background=ROW_ALT, foreground=DARK)
        for i, cal in enumerate(self.saved_calibrations):
            self.cal_tree.insert("", tk.END,
                                 tags=("even" if i % 2 == 0 else "odd",),
                                 values=tuple(cal[k] for k in CAL_FIELDS))

    def _refresh_cal_treeview(self, progress_cb=None):
        self._refresh_cal_treeview_display()
        self._apply_all_calibrations(progress_cb=progress_cb)
