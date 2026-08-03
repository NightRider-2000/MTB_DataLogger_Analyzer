import csv
import math
import os
import tkinter as tk
import warnings
from tkinter import filedialog, ttk
from PIL import Image, ImageTk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import widgets as w
from constants import BG, DARK, FIELD, ROW_ALT, GRID, TABLE_GRID, BTN_FG


_BIKE_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "__UserFiles", "Bike_Picture.jpeg")
_IMG_W, _IMG_H = 540, 300   # display size

# Default motion ratio data
_DEFAULT_SHOCK  = [0.00, 1.91, 3.86, 5.85, 7.87, 9.93, 12.03, 14.18, 16.36,
                   18.58, 20.84, 23.14, 25.48, 27.85, 30.26, 32.70, 35.17,
                   37.67, 40.21, 42.77, 45.36, 47.97, 50.60, 53.25, 55.93]
_DEFAULT_WHEEL  = [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78,
                   84, 90, 96, 102, 108, 114, 120, 126, 132, 138, 144]

# Cassette default: (Gear, Teeth) sorted by teeth ascending
_DEFAULT_CASSETTE = [
    (12, 10), (11, 12), (10, 14), (9, 16), (8, 18), (7, 21),
    (6, 24),  (5, 28),  (4, 32),  (3, 36), (2, 42), (1, 52),
]




class BikeParamsMixin:

    def _build_bike_params_tab(self):
        outer = tk.Frame(self.bike_params_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)
        for c in (0, 1, 2):
            outer.columnconfigure(c, weight=1, uniform="bp")
        outer.rowconfigure(0, weight=1)

        _EW = 7   # uniform entry width
        _LBL_FONT = ("", 11, "bold")   # row-label font (small enough to not clip)
        # Shared column geometry for the two LEFT cards so their boxes line up.
        _COL0_MIN, _COL_ENT = 180, 68   # label col ≥ longest label; entry cols

        # ── Card / table builders ────────────────────────────────────────────
        def _card(parent, title, **pack_kw):
            """A titled, bordered section that reads like a table.

            The 1-px TABLE_GRID outline is a colored outer frame with the
            content in an inner frame (reliable on macOS, where a Frame's
            ``highlightthickness`` border can silently fail to paint depending
            on anchor/position). ``pack_kw`` positions the whole card.
            """
            border = tk.Frame(parent, bg=TABLE_GRID)
            border.pack(**pack_kw)
            card = tk.Frame(border, bg=BG)
            card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
            tk.Label(card, text=title, bg=DARK, fg=BTN_FG, font=("", 14, "bold"),
                     pady=3).grid(row=0, column=0, columnspan=4, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            return card

        def _reg(var_attr, default, entry=None, entry_attr=None):
            setattr(self, var_attr, tk.StringVar(value=default))
            if entry_attr and entry is not None:
                setattr(self, entry_attr, entry)

        def _bind(entry, var_attr, cb):
            def _c(ev, _e=entry, _va=var_attr, _cb=cb):
                getattr(self, _va).set(_e.get())
                if _cb:
                    _cb()
            entry.bind("<KeyRelease>", _c)

        def _fr_header(card):
            tk.Label(card, text="Front", bg=BG, fg=DARK, font=("", 12, "bold")).grid(
                row=1, column=1, pady=(3, 0))
            tk.Label(card, text="Rear", bg=BG, fg=DARK, font=("", 12, "bold")).grid(
                row=1, column=2, pady=(3, 0))

        def _fr_row(card, row, label, unit, f_def, f_var, r_def, r_var,
                    f_cb=None, r_cb=None, f_ea=None, r_ea=None):
            tk.Label(card, text=label, bg=BG, fg=DARK, font=_LBL_FONT,
                     anchor="e").grid(row=row, column=0, sticky="e", padx=(8, 6), pady=2)
            ef = w.make_entry(card, width=_EW); ef.insert(0, f_def)
            ef.grid(row=row, column=1, padx=3, pady=2)
            er = w.make_entry(card, width=_EW); er.insert(0, r_def)
            er.grid(row=row, column=2, padx=3, pady=2)
            tk.Label(card, text=unit, bg=BG, fg=DARK, anchor="w").grid(
                row=row, column=3, sticky="w", padx=(4, 8), pady=2)
            _reg(f_var, f_def, ef, f_ea); _reg(r_var, r_def, er, r_ea)
            _bind(ef, f_var, f_cb); _bind(er, r_var, r_cb)
            return ef, er

        def _kv_row(card, row, label, default, unit, var_attr, cb=None,
                    entry_attr=None, entry_col=1, unit_col=3):
            tk.Label(card, text=label, bg=BG, fg=DARK, font=_LBL_FONT,
                     anchor="e").grid(row=row, column=0, sticky="e", padx=(8, 6), pady=2)
            e = w.make_entry(card, width=_EW); e.insert(0, default)
            e.grid(row=row, column=entry_col, pady=2)
            tk.Label(card, text=unit, bg=BG, fg=DARK, anchor="w").grid(
                row=row, column=unit_col, sticky="w", padx=(4, 8), pady=2)
            _reg(var_attr, default, e, entry_attr)
            _bind(e, var_attr, cb)
            return e

        # ── Linked-field callbacks (defined first; they read self.* entries
        # that the cards create below, and only fire on user edits) ───────────
        def _recalc(*_):
            if getattr(self, "cal_result_df", None) is not None:
                self._apply_all_calibrations()

        def _upd_fst(*_):
            # Front VERTICAL wheel travel = fork travel · sin(HTA). The trig factor
            # also scales the numerator (Front_Wheel_Pos_mm), so it cancels in
            # Front_Wheel_Pos_Perc — this MUST stay the vertical value or the front
            # sag % reads low (maxes at ~sin(HTA)·100 instead of 100%).
            try:
                self.head_tube_angle_var.set(self._head_tube_angle_entry.get())
                fst = (float(self.front_travel_var.get())
                       * math.sin(math.radians(float(self._head_tube_angle_entry.get()))))
                self._front_susp_travel_entry.delete(0, tk.END)
                self._front_susp_travel_entry.insert(0, f"{fst:.2f}")
                self.front_susp_travel_var.set(f"{fst:.6g}")
            except (ValueError, TypeError, AttributeError):
                pass
            _recalc()

        def _front_travel_cb():
            self._update_sag_plots()
            _upd_fst()

        def _rear_travel_cb():
            self._update_sag_plots()
            self._recompute_rear_wheel_travel()

        def _upd_front_center(*_):
            # Front center = wheelbase − chainstay length (derived, informational).
            try:
                fc = (float(self.wheel_base_var.get())
                      - float(self.chainstay_len_var.get()))
                self._front_center_entry.delete(0, tk.END)
                self._front_center_entry.insert(0, f"{fc:.0f}")
                self.front_center_var.set(f"{fc:.6g}")
            except (AttributeError, ValueError, tk.TclError):
                pass

        _default_fst = round(150 * math.sin(math.radians(65)), 2)

        # ── LEFT column: Suspension + Bike Geometry ───────────────────────────
        left = tk.Frame(outer, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        susp = _card(left, "Suspension", anchor="nw", padx=(4, 8))
        _fr_header(susp)
        _fr_row(susp, 2, "Spring Rate", "N/mm",
                "11.38", "front_spring_rate_var", "105.08", "rear_spring_rate_var")
        _fr_row(susp, 3, "Preload", "mm",
                "0.0", "front_preload_var", "1.93", "rear_preload_var")
        _fr_row(susp, 4, "Fork / Shock Travel", "mm",
                "150", "front_travel_var", "55", "rear_travel_var",
                f_cb=_front_travel_cb, r_cb=_rear_travel_cb,
                f_ea="_front_travel_entry", r_ea="_rear_travel_entry")
        # Rear value is a placeholder — _recompute_rear_wheel_travel() overwrites it
        # at build end (and on shock-stroke / MR-table edits) from the MR lookup.
        _fr_row(susp, 5, "Vertical Wheel Travel", "mm",
                f"{_default_fst:.2f}", "front_susp_travel_var", "150", "rear_susp_travel_var",
                f_cb=_recalc, r_cb=_recalc,
                f_ea="_front_susp_travel_entry", r_ea="_rear_susp_travel_entry")

        geo = _card(left, "Bike Geometry", anchor="nw", padx=(4, 8), pady=(12, 0))
        _kv_row(geo, 1, "Head Tube Angle", "65", "deg", "head_tube_angle_var",
                cb=_upd_fst, entry_attr="_head_tube_angle_entry", entry_col=2)
        _kv_row(geo, 2, "Wheel Base", "1242", "mm", "wheel_base_var",
                cb=_upd_front_center, entry_attr="_wheel_base_entry", entry_col=2)
        _kv_row(geo, 3, "Chainstay Length", "430", "mm", "chainstay_len_var",
                cb=_upd_front_center, entry_attr="_chainstay_len_entry", entry_col=2)
        # Front center is derived (= wheelbase − chainstay); recomputed whenever
        # either input changes and once at build end.
        _kv_row(geo, 4, "Front Center Length", "812", "mm", "front_center_var",
                entry_attr="_front_center_entry", entry_col=2)
        # BB Height = height of the bottom-bracket (load point) above the tire-
        # contact line; a geometry input for the add-on model.
        _kv_row(geo, 5, "BB Height", "340", "mm", "bb_height_var",
                cb=_recalc, entry_attr="_bb_height_entry", entry_col=2)
        _kv_row(geo, 6, "IMU Pitch Offset", "30", "deg", "pitch_offset_var",
                cb=_recalc, entry_attr="_pitch_offset_entry", entry_col=2)
        _upd_front_center()

        # Lock the two left cards to identical column widths so the Front/Rear
        # boxes — and the geometry values placed under "Rear" — line up across
        # both cards, and column 0 is always wide enough for the longest label.
        for _c in (susp, geo):
            _c.grid_columnconfigure(0, weight=0, minsize=_COL0_MIN)
            _c.grid_columnconfigure(1, minsize=_COL_ENT)
            _c.grid_columnconfigure(2, minsize=_COL_ENT)

        # ── CENTRE column: bike image + Rear Suspension Motion Ratio ──────────
        centre = tk.Frame(outer, bg=BG)
        centre.grid(row=0, column=1, sticky="nsew", pady=10)
        self._bike_params_img_label = tk.Label(centre, bg=BG)
        self._bike_params_img_label.pack()
        self.after(0, self._load_bike_params_image)

        mr_card = _card(centre, "Rear Suspension Motion Ratio",
                        anchor="n", fill=tk.BOTH, expand=True, pady=(10, 0))
        mr_card.grid_rowconfigure(2, weight=1)

        btn_frame = tk.Frame(mr_card, bg=BG)
        btn_frame.grid(row=1, column=0, columnspan=4, pady=4)
        w.make_btn(btn_frame, "Load CSV", self._load_mr_csv).pack(side=tk.LEFT, padx=(0, 4))
        w.make_btn(btn_frame, "Save CSV", self._save_mr_csv).pack(side=tk.LEFT)

        tree_frame = tk.Frame(mr_card, bg=BG)
        tree_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=6)
        mr_tree = ttk.Treeview(tree_frame, columns=("Shock_Travel", "Wheel_Vertical_Travel"),
                               show="headings", height=10)
        mr_tree.heading("Shock_Travel",          text="Shock Travel")
        mr_tree.heading("Wheel_Vertical_Travel",  text="Wheel Vert Travel")
        mr_tree.column("Shock_Travel",           width=100, anchor="center")
        mr_tree.column("Wheel_Vertical_Travel",  width=140, anchor="center")
        w.enable_gridlines(mr_tree)
        mr_tree.tag_configure("even", background=FIELD,   foreground=DARK)
        mr_tree.tag_configure("odd",  background=ROW_ALT, foreground=DARK)
        for i, (st, wt) in enumerate(zip(_DEFAULT_SHOCK, _DEFAULT_WHEEL)):
            mr_tree.insert("", tk.END, values=(st, wt), tags=("even" if i % 2 == 0 else "odd",))
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=mr_tree.yview)
        mr_tree.configure(yscrollcommand=scroll.set)
        mr_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.mr_tree = mr_tree
        mr_tree.bind("<Double-1>", self._edit_mr_cell)

        mr_plot = tk.Frame(mr_card, bg=BG)
        mr_plot.grid(row=3, column=0, columnspan=4, pady=(4, 6))
        self._fig_mr = w.make_figure(figsize=(4, 2.0), dpi=100)
        self._ax_mr  = self._fig_mr.add_subplot(111)
        self._canvas_mr = FigureCanvasTkAgg(self._fig_mr, master=mr_plot)
        self._canvas_mr.get_tk_widget().pack(anchor="center")

        # ── RIGHT column: Drivetrain & Wheels + Cassette Gears ────────────────
        right = tk.Frame(outer, bg=BG)
        right.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)

        dt = _card(right, "Drivetrain & Wheels", anchor="n")
        _fr_header(dt)
        _fr_row(dt, 2, "Wheel Circumference", "in",
                "91", "front_wheel_circ_var", "91", "rear_wheel_circ_var",
                f_ea="_front_wheel_circ_entry", r_ea="_rear_wheel_circ_entry")
        _fr_row(dt, 3, "Wheel Triggers/Rev", "",
                "12", "front_spoke_count_var", "12", "rear_spoke_count_var",
                f_ea="_front_spoke_count_entry", r_ea="_rear_spoke_count_entry")
        tk.Frame(dt, bg=TABLE_GRID, height=1).grid(row=4, column=0, columnspan=4,
                                                   sticky="ew", padx=6, pady=(4, 2))
        _kv_row(dt, 5, "Crank Triggers/Rev", "10", "", "chain_ring_spokes_var",
                entry_attr="_chain_ring_spokes_entry", entry_col=1, unit_col=2)
        _kv_row(dt, 6, "Chain Ring Teeth", "30", "teeth", "chain_ring_teeth_var",
                entry_attr="_chain_ring_teeth_entry", entry_col=1, unit_col=2)

        cass_card = _card(right, "Cassette Gears", anchor="n", pady=(12, 0))
        cassette_frame = tk.Frame(cass_card, bg=BG)
        cassette_frame.grid(row=1, column=0, columnspan=4, padx=6, pady=(4, 6))
        cassette_tree = ttk.Treeview(cassette_frame, columns=("Gear", "Teeth"),
                                     show="headings", height=12)
        cassette_tree.heading("Gear",  text="Gear")
        cassette_tree.heading("Teeth", text="Teeth")
        cassette_tree.column("Gear",  width=70, anchor="center")
        cassette_tree.column("Teeth", width=70, anchor="center")
        w.enable_gridlines(cassette_tree)
        cassette_tree.tag_configure("even", background=FIELD,   foreground=DARK)
        cassette_tree.tag_configure("odd",  background=ROW_ALT, foreground=DARK)
        for i, (gear, teeth) in enumerate(_DEFAULT_CASSETTE):
            cassette_tree.insert("", tk.END, values=(gear, teeth),
                                 tags=("even" if i % 2 == 0 else "odd",))
        cassette_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.cassette_tree = cassette_tree
        cassette_tree.bind("<Double-1>", self._edit_cassette_cell)

        self._refresh_mr_plot()
        self._recompute_rear_wheel_travel()

    def _load_bike_params_image(self):
        try:
            pil_img = Image.open(_BIKE_IMG).resize((_IMG_W, _IMG_H), Image.LANCZOS)
            self._bike_photo = ImageTk.PhotoImage(pil_img)
            self._bike_params_img_label.configure(image=self._bike_photo)
        except Exception:
            self._bike_params_img_label.configure(
                text="[Bike_Picture.jpeg not found]", fg=DARK, width=40, height=10)

    # ── Motion ratio helpers ──────────────────────────────────────────────────

    def _recompute_rear_wheel_travel(self, *_):
        """Derive rear VERTICAL wheel travel from the MR lookup at max shock stroke.

        Shock stroke (``rear_travel_var``) is a hard input from this page; the max
        rear wheel travel is the MR table's wheel value interpolated at that stroke
        — the very same LUT used per-sample for ``Rear_Wheel_Pos_mm``. The result is
        written into the (editable) rear Vertical Wheel Travel field so the sag %
        denominator matches the mapping, and calibrations refresh if a ride is open.
        """
        if not (hasattr(self, "mr_tree") and hasattr(self, "_rear_susp_travel_entry")):
            return
        import numpy as np
        try:
            shock_max = float(self.rear_travel_var.get())
        except (ValueError, TypeError, AttributeError):
            return
        shock_lut, wheel_lut = [], []
        for iid in self.mr_tree.get_children():
            vals = self.mr_tree.item(iid, "values")
            try:
                shock_lut.append(float(vals[0]))
                wheel_lut.append(float(vals[1]))
            except (ValueError, IndexError):
                pass
        if len(shock_lut) < 2:
            return
        rst = float(np.interp(shock_max, shock_lut, wheel_lut))
        self._rear_susp_travel_entry.delete(0, tk.END)
        self._rear_susp_travel_entry.insert(0, f"{rst:.2f}")
        self.rear_susp_travel_var.set(f"{rst:.6g}")
        if getattr(self, "cal_result_df", None) is not None:
            self._apply_all_calibrations()

    def _refresh_mr_plot(self):
        shock, wheel = [], []
        for iid in self.mr_tree.get_children():
            vals = self.mr_tree.item(iid, "values")
            try:
                shock.append(float(vals[0]))
                wheel.append(float(vals[1]))
            except (ValueError, IndexError):
                pass
        ax = self._ax_mr
        ax.clear()
        ax.set_facecolor(BG)
        import numpy as np
        if len(shock) >= 2:
            _s = np.asarray(shock, dtype=float)
            _w = np.asarray(wheel, dtype=float)
            _order = np.argsort(_s)
            _s, _w = _s[_order], _w[_order]
            # Leverage ratio = wheel travel per unit shock stroke = dWheel/dShock,
            # plotted against vertical wheel travel (the universal MTB convention).
            with np.errstate(divide="ignore", invalid="ignore"):
                _lr = np.gradient(_w, _s)
            _lr = np.where(np.isfinite(_lr), _lr, np.nan)
            ax.plot(_w, _lr, color=DARK, linewidth=2, marker="o", markersize=3)
        ax.set_title("Leverage Ratio", color=DARK, fontsize=12)
        ax.set_xlabel("Rear Suspension Vertical Travel (mm)", color=DARK, fontsize=9)
        ax.set_ylabel("Leverage Ratio",                       color=DARK, fontsize=9)
        ax.tick_params(colors=DARK, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor(DARK)
        ax.grid(True, color=GRID, linewidth=0.5, linestyle="-")
        ax.set_axisbelow(True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._fig_mr.tight_layout()
        self._canvas_mr.draw()
        if hasattr(self, "cal_result_df") and self.cal_result_df is not None:
            self._apply_all_calibrations()

    def _edit_mr_cell(self, event):
        tree = self.mr_tree
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        col_idx = int(col_id.lstrip("#")) - 1
        bbox = tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, width, height = bbox
        values = list(tree.item(row_id, "values"))
        var = tk.StringVar(value=values[col_idx])
        entry = tk.Entry(tree, textvariable=var, bg=FIELD, fg=DARK,
                         insertbackground=DARK, relief="flat")
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def commit(event=None):
            values[col_idx] = var.get()
            tree.item(row_id, values=tuple(values))
            entry.destroy()
            self._refresh_mr_plot()
            self._recompute_rear_wheel_travel()

        def cancel(event=None):
            entry.destroy()

        entry.bind("<Return>",   commit)
        entry.bind("<Tab>",      commit)
        entry.bind("<Escape>",   cancel)
        entry.bind("<FocusOut>", commit)

    def _load_mr_csv(self):
        path = filedialog.askopenfilename(
            title="Load Motion Ratio CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        self.mr_tree.delete(*self.mr_tree.get_children())
        with open(path, newline="") as f:
            for i, row in enumerate(csv.DictReader(f)):
                st = row.get("Shock_Travel", "")
                wt = row.get("Wheel_Vertical_Travel", "")
                tag = "even" if i % 2 == 0 else "odd"
                self.mr_tree.insert("", tk.END, values=(st, wt), tags=(tag,))
        self._refresh_mr_plot()
        self._recompute_rear_wheel_travel()

    def _save_mr_csv(self):
        path = filedialog.asksaveasfilename(
            title="Save Motion Ratio CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Shock_Travel", "Wheel_Vertical_Travel"])
            for iid in self.mr_tree.get_children():
                writer.writerow(self.mr_tree.item(iid, "values"))

    def _edit_cassette_cell(self, event):
        tree = self.cassette_tree
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        col_idx = int(col_id.lstrip("#")) - 1
        bbox = tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, width, height = bbox
        values = list(tree.item(row_id, "values"))
        var = tk.StringVar(value=values[col_idx])
        entry = tk.Entry(tree, textvariable=var, bg=FIELD, fg=DARK,
                         insertbackground=DARK, relief="flat")
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def commit(event=None):
            values[col_idx] = var.get()
            tree.item(row_id, values=tuple(values))
            entry.destroy()

        def cancel(event=None):
            entry.destroy()

        entry.bind("<Return>",   commit)
        entry.bind("<Tab>",      commit)
        entry.bind("<Escape>",   cancel)
        entry.bind("<FocusOut>", commit)
