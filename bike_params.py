import csv
import math
import os
import tkinter as tk
import warnings
from tkinter import filedialog, ttk
from PIL import Image, ImageTk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import widgets as w
from constants import BG, DARK, FIELD, ROW_ALT, GRID


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
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=0)
        outer.columnconfigure(2, weight=1)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=0)

        # ── Left: rear parameters + motion ratio table ────────────────────────
        left = tk.Frame(outer, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left.columnconfigure(0, weight=1)

        # Rear parameter grid
        pgrid = tk.Frame(left, bg=BG)
        pgrid.grid(row=0, column=0, pady=(10, 6))
        pgrid.columnconfigure(0, weight=1)
        pgrid.columnconfigure(1, weight=0)
        pgrid.columnconfigure(2, weight=0)

        _EW = 7   # uniform entry width

        def _pgrid_row(parent, row, label, default, unit, var_attr, entry_attr, callback=None):
            tk.Label(parent, text=label, bg=BG, fg=DARK,
                     font=("", 15, "bold"), anchor="e").grid(
                row=row, column=0, sticky="e", padx=(0, 6), pady=3)
            e = w.make_entry(parent, width=_EW)
            e.insert(0, default)
            e.grid(row=row, column=1, pady=3)
            tk.Label(parent, text=unit, bg=BG, fg=DARK,
                     anchor="w").grid(row=row, column=2, sticky="w", padx=(4, 0), pady=3)
            setattr(self, var_attr, tk.StringVar(value=default))
            setattr(self, entry_attr, e)
            def _cb(ev, _e=e, _va=var_attr, _cb2=callback):
                getattr(self, _va).set(_e.get())
                if _cb2:
                    _cb2()
            e.bind("<KeyRelease>", _cb)
            return e

        entry = _pgrid_row(pgrid, 0, "Rear Shock Max Travel",    "55",  "mm",
                           "rear_travel_var",      "_rear_travel_entry",
                           lambda: self._update_sag_plots())
        entry_rst = _pgrid_row(pgrid, 1, "Rear Suspension Max Travel", "150", "mm",
                               "rear_susp_travel_var", "_rear_susp_travel_entry")
        entry_rwc = _pgrid_row(pgrid, 2, "Rear Wheel Circumference",   "91",  "in",
                               "rear_wheel_circ_var",  "_rear_wheel_circ_entry")
        entry_rsc = _pgrid_row(pgrid, 3, "Rear Wheel Triggers/Rev",    "12",  "",
                               "rear_spoke_count_var", "_rear_spoke_count_entry")

        # Motion ratio section
        tk.Label(left, text="Rear Suspension Motion Ratio",
                 bg=BG, fg=DARK, font=("", 15, "bold")).grid(row=1, column=0, sticky="s", pady=(6, 2))

        btn_frame = tk.Frame(left, bg=BG)
        btn_frame.grid(row=2, column=0, sticky="w", pady=(0, 4))
        w.make_btn(btn_frame, "Load CSV", self._load_mr_csv).pack(side=tk.LEFT, padx=(0, 4))
        w.make_btn(btn_frame, "Save CSV", self._save_mr_csv).pack(side=tk.LEFT)

        tree_frame = tk.Frame(left, bg=BG)
        tree_frame.grid(row=3, column=0, sticky="nsew")
        left.rowconfigure(3, weight=1)

        mr_tree = ttk.Treeview(tree_frame, columns=("Shock_Travel", "Wheel_Vertical_Travel"),
                               show="headings", height=15)
        mr_tree.heading("Shock_Travel",          text="Shock_Travel")
        mr_tree.heading("Wheel_Vertical_Travel",  text="Wheel_Vertical_Travel")
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

        # ── Centre: bike image + chain ring input ─────────────────────────────
        centre = tk.Frame(outer, bg=BG)
        centre.grid(row=0, column=1, sticky="nsew", pady=10)
        self._bike_params_img_label = tk.Label(centre, bg=BG)
        self._bike_params_img_label.pack()
        self.after(0, self._load_bike_params_image)

        ctr_grid = tk.Frame(centre, bg=BG)
        ctr_grid.pack(pady=(8, 0))

        tk.Label(ctr_grid, text="Crank Triggers/Rev", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=3)
        self.chain_ring_spokes_var = tk.StringVar(value="10")
        entry_crs = w.make_entry(ctr_grid, width=_EW)
        entry_crs.insert(0, "10")
        entry_crs.grid(row=0, column=1, pady=3)
        def _on_crs_change(e):
            self.chain_ring_spokes_var.set(entry_crs.get())
        entry_crs.bind("<KeyRelease>", _on_crs_change)
        self._chain_ring_spokes_entry = entry_crs

        tk.Label(ctr_grid, text="Chain Ring Teeth", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=3)
        self.chain_ring_teeth_var = tk.StringVar(value="30")
        entry_crt = w.make_entry(ctr_grid, width=_EW)
        entry_crt.insert(0, "30")
        entry_crt.grid(row=1, column=1, pady=3)
        tk.Label(ctr_grid, text="teeth", bg=BG, fg=DARK).grid(row=1, column=2, sticky="w", padx=(4, 0), pady=3)
        def _on_crt_change(e):
            self.chain_ring_teeth_var.set(entry_crt.get())
        entry_crt.bind("<KeyRelease>", _on_crt_change)
        self._chain_ring_teeth_entry = entry_crt

        tk.Label(ctr_grid, text="IMU Pitch Offset", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        self.pitch_offset_var = tk.StringVar(value="30")
        entry_po = w.make_entry(ctr_grid, width=_EW)
        entry_po.insert(0, "30")
        entry_po.grid(row=2, column=1, pady=3)
        tk.Label(ctr_grid, text="deg", bg=BG, fg=DARK).grid(row=2, column=2, sticky="w", padx=(4, 0), pady=3)
        def _on_po_change(e):
            self.pitch_offset_var.set(entry_po.get())
            if hasattr(self, "cal_result_df") and self.cal_result_df is not None:
                self._apply_all_calibrations()
        entry_po.bind("<KeyRelease>", _on_po_change)
        self._pitch_offset_entry = entry_po

        # ── Right: front parameters ───────────────────────────────────────────
        right = tk.Frame(outer, bg=BG)
        right.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)
        right.columnconfigure(0, weight=1)

        pgrid2 = tk.Frame(right, bg=BG)
        pgrid2.pack(anchor="center", pady=(10, 0))
        pgrid2.columnconfigure(0, weight=1)
        pgrid2.columnconfigure(1, weight=0)
        pgrid2.columnconfigure(2, weight=0)

        def _pgrid2_row(row, label, default, unit, var_attr, entry_attr, callback=None):
            tk.Label(pgrid2, text=label, bg=BG, fg=DARK,
                     font=("", 15, "bold"), anchor="e").grid(
                row=row, column=0, sticky="e", padx=(0, 6), pady=3)
            e = w.make_entry(pgrid2, width=_EW)
            e.insert(0, default)
            e.grid(row=row, column=1, pady=3)
            tk.Label(pgrid2, text=unit, bg=BG, fg=DARK,
                     anchor="w").grid(row=row, column=2, sticky="w", padx=(4, 0), pady=3)
            setattr(self, var_attr, tk.StringVar(value=default))
            setattr(self, entry_attr, e)
            def _cb(ev, _e=e, _va=var_attr, _cb2=callback):
                getattr(self, _va).set(_e.get())
                if _cb2:
                    _cb2()
            e.bind("<KeyRelease>", _cb)
            return e

        self.front_travel_var = tk.StringVar(value="150")
        entry2 = w.make_entry(pgrid2, width=_EW)
        entry2.insert(0, "150")
        tk.Label(pgrid2, text="Front Fork Max Travel", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=3)
        entry2.grid(row=0, column=1, pady=3)
        tk.Label(pgrid2, text="mm", bg=BG, fg=DARK, anchor="w").grid(
            row=0, column=2, sticky="w", padx=(4, 0), pady=3)
        self._front_travel_entry = entry2

        self.head_tube_angle_var = tk.StringVar(value="65")
        entry3 = w.make_entry(pgrid2, width=_EW)
        entry3.insert(0, "65")
        tk.Label(pgrid2, text="Head Tube Angle", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=3)
        entry3.grid(row=1, column=1, pady=3)
        tk.Label(pgrid2, text="deg", bg=BG, fg=DARK, anchor="w").grid(
            row=1, column=2, sticky="w", padx=(4, 0), pady=3)
        self._head_tube_angle_entry = entry3

        _default_fst = round(150 * math.sin(math.radians(65)), 2)
        self.front_susp_travel_var = tk.StringVar(value=str(_default_fst))
        entry_fst = w.make_entry(pgrid2, width=_EW)
        entry_fst.insert(0, f"{_default_fst:.2f}")
        tk.Label(pgrid2, text="Front Suspension Max Travel", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        entry_fst.grid(row=2, column=1, pady=3)
        tk.Label(pgrid2, text="mm", bg=BG, fg=DARK, anchor="w").grid(
            row=2, column=2, sticky="w", padx=(4, 0), pady=3)
        self._front_susp_travel_entry = entry_fst

        entry_fwc = _pgrid2_row(3, "Front Wheel Circumference", "91", "in",
                                "front_wheel_circ_var", "_front_wheel_circ_entry")
        entry_fsc = _pgrid2_row(4, "Front Wheel Triggers/Rev",  "12", "",
                                "front_spoke_count_var", "_front_spoke_count_entry")

        # Callbacks for computed/linked fields
        def _update_front_susp_travel(*_):
            self.head_tube_angle_var.set(entry3.get())
            try:
                fst = float(self.front_travel_var.get()) * math.sin(math.radians(float(entry3.get())))
                entry_fst.delete(0, tk.END)
                entry_fst.insert(0, f"{fst:.2f}")
                self.front_susp_travel_var.set(f"{fst:.6g}")
            except (ValueError, TypeError):
                pass
            if hasattr(self, "cal_result_df") and self.cal_result_df is not None:
                self._apply_all_calibrations()

        def _on_front_change(e):
            self.front_travel_var.set(entry2.get())
            self._update_sag_plots()

        def _on_fst_change(e):
            self.front_susp_travel_var.set(entry_fst.get())
            if hasattr(self, "cal_result_df") and self.cal_result_df is not None:
                self._apply_all_calibrations()

        entry2.bind("<KeyRelease>", lambda e: (_on_front_change(e), _update_front_susp_travel()))
        entry3.bind("<KeyRelease>", _update_front_susp_travel)
        entry_fst.bind("<KeyRelease>", _on_fst_change)

        # ── Bottom centre: cassette table ─────────────────────────────────────
        cass_bot = tk.Frame(outer, bg=BG)
        cass_bot.grid(row=1, column=1, sticky="n", pady=(0, 10))
        tk.Label(cass_bot, text="Cassette", bg=BG, fg=DARK,
                 font=("", 15, "bold")).pack(pady=(4, 2))
        cassette_frame = tk.Frame(cass_bot, bg=BG)
        cassette_frame.pack(anchor="center")
        cassette_tree = ttk.Treeview(cassette_frame, columns=("Gear", "Teeth"),
                                     show="headings", height=5)
        cassette_tree.heading("Gear",  text="Gear")
        cassette_tree.heading("Teeth", text="Teeth")
        cassette_tree.column("Gear",  width=60, anchor="center")
        cassette_tree.column("Teeth", width=60, anchor="center")
        w.enable_gridlines(cassette_tree)
        cassette_tree.tag_configure("even", background=FIELD,   foreground=DARK)
        cassette_tree.tag_configure("odd",  background=ROW_ALT, foreground=DARK)
        for i, (gear, teeth) in enumerate(_DEFAULT_CASSETTE):
            cassette_tree.insert("", tk.END, values=(gear, teeth),
                                 tags=("even" if i % 2 == 0 else "odd",))
        cassette_scroll = ttk.Scrollbar(cassette_frame, orient="vertical",
                                        command=cassette_tree.yview)
        cassette_tree.configure(yscrollcommand=cassette_scroll.set)
        cassette_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cassette_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cassette_tree = cassette_tree
        cassette_tree.bind("<Double-1>", self._edit_cassette_cell)

        # Wheel Base field below cassette table
        wb_frame = tk.Frame(cass_bot, bg=BG)
        wb_frame.pack(pady=(6, 0))
        tk.Label(wb_frame, text="Wheel Base", bg=BG, fg=DARK,
                 font=("", 15, "bold"), anchor="e").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=3)
        self.wheel_base_var = tk.StringVar(value="1242")
        entry_wb = w.make_entry(wb_frame, width=_EW)
        entry_wb.insert(0, "1242")
        entry_wb.grid(row=0, column=1, pady=3)
        tk.Label(wb_frame, text="mm", bg=BG, fg=DARK,
                 anchor="w").grid(row=0, column=2, sticky="w", padx=(4, 0), pady=3)
        def _on_wb_change(e):
            self.wheel_base_var.set(entry_wb.get())
        entry_wb.bind("<KeyRelease>", _on_wb_change)
        self._wheel_base_entry = entry_wb

        # ── Bottom left: motion ratio plot ────────────────────────────────────
        bot = tk.Frame(outer, bg=BG)
        bot.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        self._fig_mr = w.make_figure(figsize=(4, 2.2), dpi=100)
        self._ax_mr  = self._fig_mr.add_subplot(111)
        self._canvas_mr = FigureCanvasTkAgg(self._fig_mr, master=bot)
        self._canvas_mr.get_tk_widget().pack(anchor="center", pady=5)
        self._refresh_mr_plot()

    def _load_bike_params_image(self):
        try:
            pil_img = Image.open(_BIKE_IMG).resize((_IMG_W, _IMG_H), Image.LANCZOS)
            self._bike_photo = ImageTk.PhotoImage(pil_img)
            self._bike_params_img_label.configure(image=self._bike_photo)
        except Exception:
            self._bike_params_img_label.configure(
                text="[Bike_Picture.jpeg not found]", fg=DARK, width=40, height=10)

    # ── Motion ratio helpers ──────────────────────────────────────────────────

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
        ax.plot(shock, wheel, color=DARK, linewidth=2)
        ax.set_title("Rear Suspension Motion Ratio", color=DARK, fontsize=13)
        ax.set_xlabel("Shock Travel (mm)",           color=DARK, fontsize=12)
        ax.set_ylabel("Wheel Vertical Travel (mm)",  color=DARK, fontsize=12)
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
