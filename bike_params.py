import csv
import math
import tkinter as tk
from tkinter import filedialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import widgets as w
from constants import BG, DARK, FIELD, ROW_ALT, GRID


# ── Bike cartoon coordinates (canvas 540 x 300) ──────────────────────────────
_CW, _CH = 540, 300

_RW  = (130, 210)
_FW  = (410, 210)
_R   = 68
_TW  = 11
_BB  = (238, 200)
_STT = (222,  90)
_HT  = (390, 102)
_HTB = (402, 145)
_PIV = (230, 158)

# Default motion ratio data
_DEFAULT_SHOCK  = [0.00, 1.91, 3.86, 5.85, 7.87, 9.93, 12.03, 14.18, 16.36,
                   18.58, 20.84, 23.14, 25.48, 27.85, 30.26, 32.70, 35.17,
                   37.67, 40.21, 42.77, 45.36, 47.97, 50.60, 53.25, 55.93]
_DEFAULT_WHEEL  = [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78,
                   84, 90, 96, 102, 108, 114, 120, 126, 132, 138, 144]


def _spokes(canvas, cx, cy, r, hub_r, n=8):
    for i in range(n):
        a = math.radians(i * 180 / n)
        canvas.create_line(
            cx + hub_r * math.cos(a), cy + hub_r * math.sin(a),
            cx + r      * math.cos(a), cy + r      * math.sin(a),
            fill=DARK, width=1,
        )
        canvas.create_line(
            cx - hub_r * math.cos(a), cy - hub_r * math.sin(a),
            cx - r      * math.cos(a), cy - r      * math.sin(a),
            fill=DARK, width=1,
        )


def _draw_bike(canvas):
    c = canvas
    fw_x, fw_y = _FW
    r = _R

    rim_r = r - _TW - 1
    for cx, cy in (_RW, _FW):
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=DARK, width=_TW)
        c.create_oval(cx-rim_r, cy-rim_r, cx+rim_r, cy+rim_r, outline=DARK, width=1)
        _spokes(c, cx, cy, rim_r - 2, 5)
        c.create_oval(cx-5, cy-5, cx+5, cy+5, fill=DARK, outline=DARK)

    c.create_line(*_BB, *_RW, fill=DARK, width=3)
    c.create_line(*_RW, *_PIV, fill=DARK, width=3)
    c.create_oval(_PIV[0]-4, _PIV[1]-4, _PIV[0]+4, _PIV[1]+4, fill=DARK, outline=DARK)

    shock_top = (226, 118)
    shock_bot = (242, 180)
    shock_mid = ((shock_top[0]+shock_bot[0])//2, (shock_top[1]+shock_bot[1])//2)
    c.create_line(*shock_top, *shock_mid, fill=DARK, width=7)
    c.create_line(*shock_mid, *shock_bot, fill=DARK, width=3)

    c.create_line(*_BB, *_STT, fill=DARK, width=5)
    c.create_line(*_STT, *_HT,  fill=DARK, width=4)
    c.create_line(*_BB, *_HTB, fill=DARK, width=5)
    c.create_line(*_HT, *_HTB, fill=DARK, width=7)

    for dx in (-6, 6):
        c.create_line(_HTB[0]+dx, _HTB[1], fw_x+dx, fw_y, fill=DARK, width=4)
    c.create_line(fw_x-6, fw_y-30, fw_x+6, fw_y-30, fill=DARK, width=3)

    stem_ex, stem_ey = _HT[0] + 18, _HT[1] - 12
    c.create_line(*_HT, stem_ex, stem_ey, fill=DARK, width=4)
    c.create_line(stem_ex, stem_ey - 20, stem_ex, stem_ey + 14, fill=DARK, width=4)

    sp_top = (_STT[0] - 2, _STT[1] - 18)
    c.create_line(*_STT, *sp_top, fill=DARK, width=3)
    c.create_line(sp_top[0]-22, sp_top[1], sp_top[0]+16, sp_top[1], fill=DARK, width=5)

    c.create_line(_BB[0], _BB[1], _BB[0]+18, _BB[1]+8,  fill=DARK, width=3)
    c.create_line(_BB[0], _BB[1], _BB[0]-18, _BB[1]-8, fill=DARK, width=3)
    cr = 14
    c.create_oval(_BB[0]-cr, _BB[1]-cr, _BB[0]+cr, _BB[1]+cr, outline=DARK, width=2)


class BikeParamsMixin:

    def _build_bike_params_tab(self):
        outer = tk.Frame(self.bike_params_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=0)
        outer.columnconfigure(2, weight=1)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=0)

        # ── Left: rear suspension + motion ratio table ────────────────────────
        left = tk.Frame(outer, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        left.columnconfigure(0, weight=1)

        tk.Label(left, text="Rear Shock Max Travel",
                 bg=BG, fg=DARK, font=("", 11, "bold")).grid(row=0, column=0, pady=(20, 4))
        self.rear_travel_var = tk.StringVar(value="55")
        rear_frame = tk.Frame(left, bg=BG)
        rear_frame.grid(row=1, column=0, pady=(0, 16))
        entry = w.make_entry(rear_frame, width=6)
        entry.insert(0, "55")
        entry.pack(side=tk.LEFT)
        def _on_rear_change(e):
            self.rear_travel_var.set(entry.get())
            self._update_sag_plots()
        entry.bind("<KeyRelease>", _on_rear_change)
        self._rear_travel_entry = entry
        tk.Label(rear_frame, text=" mm", bg=BG, fg=DARK).pack(side=tk.LEFT)

        tk.Label(left, text="Rear Suspension Motion Ratio",
                 bg=BG, fg=DARK, font=("", 10, "bold")).grid(row=2, column=0, sticky="s", pady=(10, 2))

        # CSV buttons
        btn_frame = tk.Frame(left, bg=BG)
        btn_frame.grid(row=3, column=0, sticky="w", pady=(0, 4))
        w.make_btn(btn_frame, "Load CSV", self._load_mr_csv).pack(side=tk.LEFT, padx=(0, 4))
        w.make_btn(btn_frame, "Save CSV", self._save_mr_csv).pack(side=tk.LEFT)

        # Table
        tree_frame = tk.Frame(left, bg=BG)
        tree_frame.grid(row=4, column=0, sticky="nsew")
        left.rowconfigure(4, weight=1)

        mr_tree = ttk.Treeview(tree_frame, columns=("Shock_Travel", "Wheel_Vertical_Travel"),
                               show="headings", height=15)
        mr_tree.heading("Shock_Travel",          text="Shock_Travel")
        mr_tree.heading("Wheel_Vertical_Travel",  text="Wheel_Vertical_Travel")
        mr_tree.column("Shock_Travel",           width=100, anchor="center")
        mr_tree.column("Wheel_Vertical_Travel",  width=140, anchor="center")
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

        # ── Centre: bike cartoon ──────────────────────────────────────────────
        centre = tk.Frame(outer, bg=BG)
        centre.grid(row=0, column=1, sticky="nsew", pady=10)
        bike_canvas = tk.Canvas(centre, width=_CW, height=_CH, bg=BG, highlightthickness=0)
        bike_canvas.pack()
        _draw_bike(bike_canvas)

        # ── Right: front suspension ───────────────────────────────────────────
        right = tk.Frame(outer, bg=BG)
        right.grid(row=0, column=2, sticky="nsew", padx=20, pady=20)
        right.columnconfigure(0, weight=1)

        tk.Label(right, text="Front Fork Max Travel",
                 bg=BG, fg=DARK, font=("", 11, "bold")).pack(anchor="center", pady=(40, 6))
        self.front_travel_var = tk.StringVar(value="150")
        front_frame = tk.Frame(right, bg=BG)
        front_frame.pack(anchor="center")
        entry2 = w.make_entry(front_frame, width=6)
        entry2.insert(0, "150")
        entry2.pack(side=tk.LEFT)
        def _on_front_change(e):
            self.front_travel_var.set(entry2.get())
            self._update_sag_plots()
        entry2.bind("<KeyRelease>", _on_front_change)
        self._front_travel_entry = entry2
        tk.Label(front_frame, text=" mm", bg=BG, fg=DARK).pack(side=tk.LEFT)

        tk.Label(right, text="Head Tube Angle",
                 bg=BG, fg=DARK, font=("", 11, "bold")).pack(anchor="center", pady=(20, 6))
        self.head_tube_angle_var = tk.StringVar(value="65")
        ht_frame = tk.Frame(right, bg=BG)
        ht_frame.pack(anchor="center")
        entry3 = w.make_entry(ht_frame, width=6)
        entry3.insert(0, "65")
        entry3.pack(side=tk.LEFT)
        def _on_hta_change(e):
            self.head_tube_angle_var.set(entry3.get())
            if hasattr(self, "cal_result_df") and self.cal_result_df is not None:
                self._apply_all_calibrations()
        entry3.bind("<KeyRelease>", _on_hta_change)
        self._head_tube_angle_entry = entry3
        tk.Label(ht_frame, text=" deg", bg=BG, fg=DARK).pack(side=tk.LEFT)

        # ── Bottom centre: motion ratio plot ──────────────────────────────────
        bot = tk.Frame(outer, bg=BG)
        bot.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        self._fig_mr = w.make_figure(figsize=(4, 2.2), dpi=100)
        self._ax_mr  = self._fig_mr.add_subplot(111)
        self._canvas_mr = FigureCanvasTkAgg(self._fig_mr, master=bot)
        self._canvas_mr.get_tk_widget().pack(anchor="center", pady=5)
        self._refresh_mr_plot()

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
        ax.set_title("Rear Suspension Motion Ratio", color=DARK, fontsize=9)
        ax.set_xlabel("Shock Travel (mm)",           color=DARK, fontsize=8)
        ax.set_ylabel("Wheel Vertical Travel (mm)",  color=DARK, fontsize=8)
        ax.tick_params(colors=DARK, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor(DARK)
        ax.grid(True, color=GRID, linewidth=0.5, linestyle="-")
        ax.set_axisbelow(True)
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
