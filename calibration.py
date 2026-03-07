import csv
import tkinter as tk
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

    def _sync_form_to_table(self, event=None):
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
                try:
                    raw_min, raw_max, cal_min, cal_max = self._read_cal_fields()
                    bias = float(self.bias_entry.get()) if self.bias_entry.get().strip() else 0.0
                    if raw_max != raw_min and self.df is not None:
                        a = (cal_max - cal_min) / (raw_max - raw_min)
                        b = cal_min - a * raw_min
                        result = a * self.df[col] + b - bias
                        cal["Calibrated_Min"] = round(result.min(), 6)
                        cal["Calibrated_Max"] = round(result.max(), 6)
                    else:
                        cal["Calibrated_Min"] = float("nan")
                        cal["Calibrated_Max"] = float("nan")
                except ValueError:
                    cal["Calibrated_Min"] = float("nan")
                    cal["Calibrated_Max"] = float("nan")
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
            self.new_signal_entry.set("")

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

        # Override with edge-detected result if available in cal_result_df
        if (self.cal_result_df is not None
                and new_name in self.cal_result_df.columns):
            calibrated = self.cal_result_df[new_name]

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
            data  = calibrated.dropna()
            color = HIST_BAR_COLOR
            mean, med, std, mn, mx = data.mean(), data.median(), data.std(), data.min(), data.max()
            self.ax_hist_cal.hist(data, bins=200, alpha=0.55, color=color)
            self.ax_hist_cal.axvline(mean, color=color, linestyle="--", linewidth=1.5)
            self.ax_hist_cal.axvline(med,  color=color, linestyle=":",  linewidth=1.5)
            self.ax_hist_cal.axvline(mn,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist_cal.axvline(mx,   color=color, linestyle="--", linewidth=1.5)
            self.ax_hist_cal.axvspan(mean - std, mean + std, alpha=0.12, color=color)
            stats_text = f"{new_name}\n  mean={mean:.4g}\n  med ={med:.4g}\n  std ={std:.4g}\n  min ={mn:.4g}\n  max ={mx:.4g}"
            self.ax_hist_cal.text(
                0.97, 0.97, stats_text,
                transform=self.ax_hist_cal.transAxes, fontsize=7,
                verticalalignment="top", horizontalalignment="right", color=DARK,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=GRID, alpha=0.9),
            )
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

    def _apply_all_calibrations(self):
        if self.df is None:
            return
        import math
        import pandas as pd
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

        # Rotate board-frame IMU signals → ISO vehicle frame (X fwd, Y left, Z up).
        # Board mounting: X mostly down, Y mostly forward, Z lateral.
        # Verified at rest: raw aX_g ≈ -cos(θ)·g, aY_g ≈ -sin(θ)·g at pitch_offset θ.
        if "aX_g" in self.cal_result_df.columns and "aY_g" in self.cal_result_df.columns:
            import numpy as np
            try:
                _theta = np.radians(float(self.pitch_offset_var.get()))
            except (AttributeError, ValueError):
                _theta = np.radians(30.5)
            _ax = self.cal_result_df["aX_g"].values.astype(float)
            _ay = self.cal_result_df["aY_g"].values.astype(float)
            _az = self.cal_result_df["aZ_g"].values.astype(float) if "aZ_g" in self.cal_result_df.columns else np.zeros(len(_ax))
            # ISO X=fwd (0g rest), Z=up (+1g rest), Y=lateral
            self.cal_result_df["aFwd_g"]  = -(np.sin(_theta) * _ax - np.cos(_theta) * _ay)
            self.cal_result_df["aVert_g"] = -np.cos(_theta) * _ax - np.sin(_theta) * _ay
            self.cal_result_df["aLat_g"]  = _az
            self.cal_result_df.drop(columns=[c for c in ["aX_g", "aY_g", "aZ_g"]
                                             if c in self.cal_result_df.columns], inplace=True)

            # Gyros: same rotation for gX/gY; gZ (lateral) = pure pitch rate
            if "gX_dps" in self.cal_result_df.columns and "gY_dps" in self.cal_result_df.columns:
                _gx = self.cal_result_df["gX_dps"].values.astype(float)
                _gy = self.cal_result_df["gY_dps"].values.astype(float)
                _gz = self.cal_result_df["gZ_dps"].values.astype(float) if "gZ_dps" in self.cal_result_df.columns else np.zeros(len(_gx))
                self.cal_result_df["gRoll_dps"]  =  np.sin(_theta) * _gx - np.cos(_theta) * _gy
                self.cal_result_df["gYaw_dps"]   = -np.cos(_theta) * _gx - np.sin(_theta) * _gy
                self.cal_result_df["gPitch_dps"] = _gz
                self.cal_result_df.drop(columns=[c for c in ["gX_dps", "gY_dps", "gZ_dps"]
                                                 if c in self.cal_result_df.columns], inplace=True)

            # Magnetometer: same rotation
            if "mX_uT" in self.cal_result_df.columns and "mY_uT" in self.cal_result_df.columns:
                _mx = self.cal_result_df["mX_uT"].values.astype(float)
                _my = self.cal_result_df["mY_uT"].values.astype(float)
                _mz = self.cal_result_df["mZ_uT"].values.astype(float) if "mZ_uT" in self.cal_result_df.columns else np.zeros(len(_mx))
                self.cal_result_df["mFwd_uT"]  =  np.sin(_theta) * _mx - np.cos(_theta) * _my
                self.cal_result_df["mVert_uT"] = -np.cos(_theta) * _mx - np.sin(_theta) * _my
                self.cal_result_df["mLat_uT"]  = _mz
                self.cal_result_df.drop(columns=[c for c in ["mX_uT", "mY_uT", "mZ_uT"]
                                                 if c in self.cal_result_df.columns], inplace=True)

        # Crank speed RPM from falling-edge detection
        _crank_cal = next((c for c in self.saved_calibrations
                           if c.get("Calibrated_Name", "").strip() == "Crank_Spd_rpm"), None)
        if (_crank_cal and _crank_cal.get("Signal") in self.df.columns
                and hasattr(self, "chain_ring_spokes_var")):
            import numpy as np
            try:
                n_spokes = max(1, int(float(self.chain_ring_spokes_var.get())))
                _perc = 0.70
                raw = self.df[_crank_cal["Signal"]].dropna()
                if len(raw) > n_spokes * 2:
                    threshold = raw.quantile(0.02) + (raw.quantile(0.98) - raw.quantile(0.02)) * _perc
                    binary = (raw > threshold).astype(int)
                    falling = binary.diff() == -1
                    edge_times = raw.index[falling]
                    if len(edge_times) > n_spokes:
                        rpm_vals, rpm_times = [], []
                        for i in range(n_spokes, len(edge_times)):
                            dt = (edge_times[i] - edge_times[i - n_spokes]).total_seconds()
                            if dt > 0:
                                rpm_vals.append(60.0 / dt)
                                rpm_times.append(edge_times[i])
                        if rpm_vals:
                            tmp = pd.Series(rpm_vals, index=pd.DatetimeIndex(rpm_times), dtype=float)
                            self.cal_result_df["Crank_Spd_rpm"] = tmp.reindex(self.df.index).ffill(limit=20)
            except Exception as e:
                print(f"Crank speed calc error: {e}")

        # Front wheel speed MPH from falling-edge detection
        _frt_spd_cal = next((c for c in self.saved_calibrations
                             if c.get("Calibrated_Name", "").strip() == "Front_Horz_Wheel_Spd_mph"), None)
        if (_frt_spd_cal and _frt_spd_cal.get("Signal") in self.df.columns
                and hasattr(self, "front_spoke_count_var")
                and hasattr(self, "front_wheel_circ_var")):
            import numpy as np
            try:
                n_spokes  = max(1, int(float(self.front_spoke_count_var.get())))
                circ_in   = float(self.front_wheel_circ_var.get())   # inches per revolution
                _perc = 0.70
                raw = self.df[_frt_spd_cal["Signal"]].dropna()
                if len(raw) > n_spokes * 2:
                    threshold = raw.quantile(0.02) + (raw.quantile(0.98) - raw.quantile(0.02)) * _perc
                    binary = (raw > threshold).astype(int)
                    falling = binary.diff() == -1
                    edge_times = raw.index[falling]
                    if len(edge_times) > n_spokes:
                        spd_vals, spd_times = [], []
                        for i in range(n_spokes, len(edge_times)):
                            dt = (edge_times[i] - edge_times[i - n_spokes]).total_seconds()
                            if dt > 0:
                                spd_vals.append(circ_in * 3600.0 / (63360.0 * dt))
                                spd_times.append(edge_times[i])
                        if spd_vals:
                            tmp = pd.Series(spd_vals, index=pd.DatetimeIndex(spd_times), dtype=float)
                            self.cal_result_df["Front_Horz_Wheel_Spd_mph"] = tmp.reindex(self.df.index).ffill(limit=20)
            except Exception as e:
                print(f"Front wheel speed calc error: {e}")

        # Rear wheel speed MPH from falling-edge detection
        _rr_spd_cal = next((c for c in self.saved_calibrations
                            if c.get("Calibrated_Name", "").strip() == "Rear_Horz_Wheel_Spd_mph"), None)
        if (_rr_spd_cal and _rr_spd_cal.get("Signal") in self.df.columns
                and hasattr(self, "rear_spoke_count_var")
                and hasattr(self, "rear_wheel_circ_var")):
            import numpy as np
            try:
                n_spokes  = max(1, int(float(self.rear_spoke_count_var.get())))
                circ_in   = float(self.rear_wheel_circ_var.get())   # inches per revolution
                _perc = 0.70
                raw = self.df[_rr_spd_cal["Signal"]].dropna()
                if len(raw) > n_spokes * 2:
                    threshold = raw.quantile(0.02) + (raw.quantile(0.98) - raw.quantile(0.02)) * _perc
                    binary = (raw > threshold).astype(int)
                    falling = binary.diff() == -1
                    edge_times = raw.index[falling]
                    if len(edge_times) > n_spokes:
                        spd_vals, spd_times = [], []
                        for i in range(n_spokes, len(edge_times)):
                            dt = (edge_times[i] - edge_times[i - n_spokes]).total_seconds()
                            if dt > 0:
                                spd_vals.append(circ_in * 3600.0 / (63360.0 * dt))
                                spd_times.append(edge_times[i])
                        if spd_vals:
                            tmp = pd.Series(spd_vals, index=pd.DatetimeIndex(spd_times), dtype=float)
                            self.cal_result_df["Rear_Horz_Wheel_Spd_mph"] = tmp.reindex(self.df.index).ffill(limit=20)
            except Exception as e:
                print(f"Rear wheel speed calc error: {e}")

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
                    self.cal_result_df["Fork_Pos_perc"] = (
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
                    self.cal_result_df["Shock_Pos_perc"] = (
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
                    self.cal_result_df["Front_Wheel_Pos_perc"] = (
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
                    self.cal_result_df["Rear_Wheel_Pos_perc"] = (
                        self.cal_result_df["Rear_Wheel_Pos_mm"] / rear_susp_max * 100
                    )
            except (ValueError, TypeError):
                pass

        # Wheel position speed (mm/s) = diff(pos_mm) / diff(time_s)
        _dt_s = self.cal_result_df.index.to_series().diff().dt.total_seconds()
        if "Front_Wheel_Pos_mm" in self.cal_result_df.columns:
            self.cal_result_df["Front_Vert_Wheel_Spd_mmPs"] = (
                self.cal_result_df["Front_Wheel_Pos_mm"].diff() / _dt_s
            )
        if "Rear_Wheel_Pos_mm" in self.cal_result_df.columns:
            self.cal_result_df["Rear_Vert_Wheel_Spd_mmPs"] = (
                self.cal_result_df["Rear_Wheel_Pos_mm"].diff() / _dt_s
            )

        # Wheel-in-air flags
        if "Front_Wheel_Pos_perc" in self.cal_result_df.columns:
            self.cal_result_df["Front_Wheel_Air"] = (
                self.cal_result_df["Front_Wheel_Pos_perc"] <= 9
            ).astype(int)
        if "Rear_Wheel_Pos_perc" in self.cal_result_df.columns:
            self.cal_result_df["Rear_Wheel_Air"] = (
                self.cal_result_df["Rear_Wheel_Pos_perc"] <= 9
            ).astype(int)

        # Dynamic sag: 0.3 Hz low-pass of Wheel_Pos_perc, mean-centred
        #   result = filtered - mean(filtered)  [% points]
        _TWO_PI_FC = 2.0 * np.pi * 0.3   # 0.3 Hz cutoff
        _dt_arr = self.cal_result_df.index.to_series().diff().dt.total_seconds().values
        for _src, _dst in [
            ("Front_Wheel_Pos_perc", "Front_Dynamic_Sag_Perc"),
            ("Rear_Wheel_Pos_perc",  "Rear_Dynamic_Sag_Perc"),
        ]:
            if _src in self.cal_result_df.columns:
                _sig = self.cal_result_df[_src].values.astype(float)
                _out = np.empty(len(_sig))
                _out[0] = _sig[0]
                for _i in range(1, len(_sig)):
                    _dt_i = _dt_arr[_i] if np.isfinite(_dt_arr[_i]) and _dt_arr[_i] > 0 else 1.0 / 67.0
                    _a    = _dt_i / (1.0 / _TWO_PI_FC + _dt_i)
                    _prev = _out[_i - 1] if np.isfinite(_out[_i - 1]) else _sig[_i]
                    _out[_i] = _a * _sig[_i] + (1.0 - _a) * _prev if np.isfinite(_sig[_i]) else _prev
                self.cal_result_df[_dst] = _out - np.nanmean(_out)

        # Gear selection: nearest cassette sprocket from crank/wheel RPM ratio
        if ("Crank_Spd_rpm" in self.cal_result_df.columns
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

                _crank_rpm = self.cal_result_df["Crank_Spd_rpm"].values.astype(float)
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

        # IMU attitude estimation — Pitch, Roll, Yaw (degrees)
        # Yaw is gyro-only integration (magnetometer excluded — subject to hard-iron distortion)
        _IMU_SIGNALS = ("aFwd_g", "aVert_g", "aLat_g",
                        "gRoll_dps", "gPitch_dps", "gYaw_dps")
        if all(s in self.cal_result_df.columns for s in _IMU_SIGNALS):
            import numpy as np
            try:
                ALPHA        = 0.98   # gyro trust fraction (tunable)
                SMOOTH_WIN   = 25     # rolling-average window (samples)

                # ISO frame: X=fwd (0g rest), Z=up (+1g rest), Y=lateral
                a_fwd  = self.cal_result_df["aFwd_g"].values.astype(float)
                a_vert = self.cal_result_df["aVert_g"].values.astype(float)
                a_lat  = self.cal_result_df["aLat_g"].values.astype(float)
                g_roll  = self.cal_result_df["gRoll_dps"].values.astype(float)
                g_pitch = self.cal_result_df["gPitch_dps"].values.astype(float)
                g_yaw   = self.cal_result_df["gYaw_dps"].values.astype(float)

                _dt_arr = (self.cal_result_df.index.to_series()
                           .diff().dt.total_seconds().fillna(0.0).values)
                n = len(a_fwd)
                pitch = np.zeros(n)
                roll  = np.zeros(n)
                yaw   = np.zeros(n)

                # Initialise from first finite accel sample
                i0 = 0
                for k in range(n):
                    if (np.isfinite(a_fwd[k]) and np.isfinite(a_vert[k])
                            and np.isfinite(a_lat[k])):
                        i0 = k
                        break

                # ISO: pitch = arctan2(-aFwd, sqrt(aLat²+aVert²)), roll = arctan2(aLat, aVert)
                pitch[i0] = np.degrees(np.arctan2(-a_fwd[i0],
                                        np.sqrt(a_lat[i0]**2 + a_vert[i0]**2)))
                roll[i0]  = np.degrees(np.arctan2(a_lat[i0], a_vert[i0]))
                yaw[i0]   = 0.0   # no absolute heading reference without magnetometer

                # Complementary filter loop — yaw is gyro-only integration
                for i in range(i0 + 1, n):
                    dt = min(_dt_arr[i], 0.1)   # cap at 100 ms (protects multi-file gaps)
                    if not (np.isfinite(a_fwd[i]) and np.isfinite(a_vert[i])
                            and np.isfinite(a_lat[i]) and np.isfinite(g_pitch[i])
                            and np.isfinite(g_roll[i]) and np.isfinite(g_yaw[i])):
                        pitch[i] = pitch[i-1];  roll[i] = roll[i-1];  yaw[i] = yaw[i-1]
                        continue
                    pitch_a = np.degrees(np.arctan2(-a_fwd[i],
                                          np.sqrt(a_lat[i]**2 + a_vert[i]**2)))
                    roll_a  = np.degrees(np.arctan2(a_lat[i], a_vert[i]))
                    pitch[i] = ALPHA*(pitch[i-1] + g_pitch[i]*dt) + (1-ALPHA)*pitch_a
                    roll[i]  = ALPHA*(roll[i-1]  + g_roll[i]*dt)  + (1-ALPHA)*roll_a
                    yaw[i]   = yaw[i-1] + g_yaw[i]*dt

                # Rolling-average post-filter (min_periods=1 avoids NaN at edges)
                _w = SMOOTH_WIN
                pitch = pd.Series(pitch).rolling(_w, center=True, min_periods=1).mean().values
                roll  = pd.Series(roll ).rolling(_w, center=True, min_periods=1).mean().values
                yaw   = pd.Series(yaw  ).rolling(_w, center=True, min_periods=1).mean().values

                self.cal_result_df["Pitch_deg"] = pitch
                self.cal_result_df["Roll_deg"]  = roll
                self.cal_result_df["Yaw_deg"]   = yaw
            except Exception:
                pass

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

        self._refresh_free_plot_signals()
        self._refresh_ts_signals()
        self._update_sag_plots()
        self._update_susp_speed_plots()
        self._update_frequency_plot()
        self._update_imu_plots()
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

    def _refresh_cal_treeview(self):
        self._refresh_cal_treeview_display()
        self._apply_all_calibrations()
