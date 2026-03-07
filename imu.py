import os
import tkinter as tk
import warnings

import numpy as np
from matplotlib.lines import Line2D
from PIL import Image, ImageTk

import widgets as w
from constants import BG, DARK, HIST_COLORS

_DIR = os.path.dirname(os.path.abspath(__file__))
_BIKE_IMG  = os.path.join(_DIR, "__UserFiles", "Bike_Picture.jpeg")
_BOARD_IMG = os.path.join(_DIR, "__UserFiles", "Board_Picture.png")

_WORLD_COLOR = "#4488ff"   # blue — ISO world-frame axes
_BOARD_COLOR = "#111111"   # near-black — board-frame axes

# Fixed signal groups — each row becomes a histogram panel
_GROUPS = [
    ("Attitude (deg)",  [("Pitch_deg",  "Pitch"), ("Roll_deg",  "Roll")]),
    ("Accel ISO (g)",   [("aFwd_g",     "Fwd"),   ("aVert_g",  "Vert"),  ("aLat_g",    "Lat")]),
    ("Gyro ISO (dps)",  [("gPitch_dps", "Pitch"), ("gRoll_dps","Roll"),  ("gYaw_dps",  "Yaw")]),
]


class ImuMixin:

    def _build_imu_tab(self):
        outer = tk.Frame(self.imu_tab, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=17)  # histograms (~85%)
        outer.columnconfigure(1, weight=3)   # images + diagram (~15%)
        outer.rowconfigure(0, weight=1)

        # ── Left: histogram rows ───────────────────────────────────────────────
        left = tk.Frame(outer, bg=BG)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        self._imu_hist_axes     = []
        self._imu_hist_figs     = []
        self._imu_hist_canvases = []

        for i, (group_label, signals) in enumerate(_GROUPS):
            left.rowconfigure(i, weight=1)
            section = tk.Frame(left, bg=BG)
            section.grid(row=i, column=0, sticky="nsew", padx=4, pady=2)
            section.columnconfigure(0, weight=1)
            section.rowconfigure(0, weight=1)

            fig = w.make_figure(figsize=(7, 2), dpi=100)
            ax  = fig.add_subplot(111)
            ax.set_facecolor(BG)
            canvas, cv_widget = w.make_canvas(fig, section)
            cv_widget.grid(row=0, column=0, sticky="nsew")

            self._imu_hist_figs.append(fig)
            self._imu_hist_axes.append(ax)
            self._imu_hist_canvases.append(canvas)

        # ── Right panel ────────────────────────────────────────────────────────
        right = tk.Frame(outer, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)   # bike picture
        right.rowconfigure(1, weight=1)   # bottom row (board pic + axis diagram)

        # Bike picture — top, full width
        self._imu_bike_label = tk.Label(right, bg=BG)
        self._imu_bike_label.grid(row=0, column=0, sticky="nsew")

        # Bottom row: board picture (left) + axis diagram (right)
        bot = tk.Frame(right, bg=BG)
        bot.grid(row=1, column=0, sticky="nsew")
        bot.columnconfigure(0, weight=7)    # board picture (~35%)
        bot.columnconfigure(1, weight=13)   # axis diagram (~65%, ~30% bigger than 50/50)
        bot.rowconfigure(0, weight=1)

        self._imu_board_label = tk.Label(bot, bg=BG)
        self._imu_board_label.grid(row=0, column=0, sticky="nsew")

        # Axis orientation diagram — right of board picture
        self._imu_axis_fig = w.make_figure(figsize=(4, 4), dpi=100)
        self._imu_axis_ax  = self._imu_axis_fig.add_subplot(111)
        self._imu_axis_ax.set_facecolor(BG)
        self._imu_axis_canvas, axis_widget = w.make_canvas(self._imu_axis_fig, bot)
        axis_widget.grid(row=0, column=1, sticky="nsew")

        self._imu_right_frame = right
        self._imu_bike_photo  = None
        self._imu_board_photo = None

        right.bind("<Configure>", self._imu_resize_images)

        # Draw diagram immediately (no data needed)
        self._draw_axis_diagram()

    # ── Axis orientation diagram ───────────────────────────────────────────────

    def _draw_axis_diagram(self):
        ax  = self._imu_axis_ax
        fig = self._imu_axis_fig
        ax.clear()
        ax.set_facecolor(BG)

        try:
            theta_deg = float(self.pitch_offset_var.get())
        except (AttributeError, ValueError):
            theta_deg = 30.5
        theta = np.radians(theta_deg)

        L = 0.78   # arrow length

        # Board-frame axes in sagittal plane (forward=right, up=up)
        # Board X: mostly down, theta from vertical toward forward
        bx = ( np.sin(theta), -np.cos(theta))
        # Board Y: mostly forward, theta above horizontal
        by = ( np.cos(theta),  np.sin(theta))

        # ISO world-frame axes
        wx = (1.0, 0.0)   # forward
        wz = (0.0, 1.0)   # up

        arrow_kw = dict(head_width=0.055, head_length=0.055,
                        length_includes_head=True, zorder=3)

        # Board axes — black
        ax.arrow(0, 0, bx[0]*L, bx[1]*L, fc=_BOARD_COLOR, ec=_BOARD_COLOR, **arrow_kw)
        ax.arrow(0, 0, by[0]*L, by[1]*L, fc=_BOARD_COLOR, ec=_BOARD_COLOR, **arrow_kw)

        # World axes — blue
        ax.arrow(0, 0, wx[0]*L, wx[1]*L, fc=_WORLD_COLOR, ec=_WORLD_COLOR, **arrow_kw)
        ax.arrow(0, 0, wz[0]*L, wz[1]*L, fc=_WORLD_COLOR, ec=_WORLD_COLOR, **arrow_kw)

        # Labels — placed beyond arrow tip, anchored away from arrow body
        lpad = 0.15
        # Board X: arrow goes lower-left in display; label below tip
        ax.text(bx[0]*(L+lpad), bx[1]*(L+lpad), "Board X",
                color=_BOARD_COLOR, fontsize=8, ha="center", va="top", fontweight="bold")
        # Board Y: arrow goes upper-left in display; label above tip
        ax.text(by[0]*(L+lpad), by[1]*(L+lpad), "Board Y",
                color=_BOARD_COLOR, fontsize=8, ha="center", va="bottom", fontweight="bold")
        # Fwd (X): arrow goes horizontally left; label above tip (clear of Board Y)
        ax.text(wx[0]*L, wx[1]*L + 0.14, "Fwd (X)",
                color=_WORLD_COLOR, fontsize=8, ha="center", va="bottom", fontweight="bold")
        # Up (Z): arrow goes straight up; label centered above tip (x=0 = center of display)
        ax.text(0, wz[1]*L + 0.05, "Up (Z)",
                color=_WORLD_COLOR, fontsize=8, ha="center", va="bottom", fontweight="bold")

        # Arc between world Fwd (0°) and Board Y (theta above horizontal)
        arc_r = 0.28
        arc1 = np.linspace(0, theta, 40)
        ax.plot(arc_r * np.cos(arc1), arc_r * np.sin(arc1),
                color=DARK, linewidth=1.2, zorder=2)
        mid1 = theta / 2
        ax.text(arc_r * 1.45 * np.cos(mid1), arc_r * 1.45 * np.sin(mid1),
                f"{theta_deg:.0f}°", color=DARK, fontsize=8, ha="center", va="center")

        # Arc between world Down (-90°) and Board X (theta - 90° from x-axis)
        bx_angle = np.arctan2(bx[1], bx[0])   # ≈ -(90° - theta)
        arc2 = np.linspace(-np.pi/2, bx_angle, 40)
        ax.plot(arc_r * np.cos(arc2), arc_r * np.sin(arc2),
                color=DARK, linewidth=1.2, zorder=2)
        mid2 = (-np.pi/2 + bx_angle) / 2
        ax.text(arc_r * 1.45 * np.cos(mid2), arc_r * 1.45 * np.sin(mid2),
                f"{theta_deg:.0f}°", color=DARK, fontsize=8, ha="center", va="center")

        # Dashed reference lines (horizontal + vertical)
        ax.axhline(0, color=DARK, linewidth=0.6, linestyle="--", alpha=0.35, zorder=1)
        ax.axvline(0, color=DARK, linewidth=0.6, linestyle="--", alpha=0.35, zorder=1)

        # Origin dot
        ax.plot(0, 0, "o", color=DARK, markersize=4, zorder=4)

        # Legend
        handles = [
            Line2D([0], [0], color=_BOARD_COLOR, lw=2, label="Board frame"),
            Line2D([0], [0], color=_WORLD_COLOR, lw=2, label="ISO world frame"),
        ]
        ax.legend(handles=handles, fontsize=6, facecolor=BG, edgecolor=DARK,
                  labelcolor=DARK, loc="lower right")

        lim = 1.05
        ax.set_xlim(lim, -lim)   # inverted so forward (positive x) points left
        ax.set_ylim(-lim, lim)
        ax.set_aspect("equal")
        ax.set_title("IMU Axis Orientation", color=DARK, fontsize=8)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fig.tight_layout()
        self._imu_axis_canvas.draw()

    # ── Image rendering ────────────────────────────────────────────────────────

    def _imu_resize_images(self, event=None):
        frame = self._imu_right_frame
        w_px  = frame.winfo_width()
        h_px  = frame.winfo_height()
        if w_px < 10 or h_px < 10:
            return
        slot_w = w_px
        slot_h = h_px // 2

        # Bike picture — flipped left-to-right
        try:
            img = Image.open(_BIKE_IMG)
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            img.thumbnail((slot_w, slot_h), Image.LANCZOS)
            self._imu_bike_photo = ImageTk.PhotoImage(img)
            self._imu_bike_label.configure(image=self._imu_bike_photo)
        except Exception:
            self._imu_bike_label.configure(text="[Bike_Picture.jpeg not found]",
                                           fg=DARK, font=("", 9))

        # Board picture — rotated 60° counter-clockwise, composited onto BG
        try:
            img = Image.open(_BOARD_IMG).convert("RGBA")
            img = img.rotate(60, expand=True, resample=Image.BICUBIC)
            bg_color = tuple(int(BG.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            bg_layer = Image.new("RGBA", img.size, bg_color)
            bg_layer.paste(img, mask=img.split()[3])
            img = bg_layer.convert("RGB")
            img.thumbnail((slot_w // 2, slot_h), Image.LANCZOS)
            self._imu_board_photo = ImageTk.PhotoImage(img)
            self._imu_board_label.configure(image=self._imu_board_photo)
        except Exception:
            self._imu_board_label.configure(text="[Board_Picture.png not found]",
                                            fg=DARK, font=("", 9))

    # ── Histogram update ───────────────────────────────────────────────────────

    def _update_imu_plots(self):
        if not hasattr(self, "_imu_hist_axes"):
            return
        if self.cal_result_df is None:
            return

        for idx, (group_label, signals) in enumerate(_GROUPS):
            ax  = self._imu_hist_axes[idx]
            fig = self._imu_hist_figs[idx]
            ax.clear()
            ax.set_facecolor(BG)

            plotted = False
            for j, (col, sig_label) in enumerate(signals):
                if col not in self.cal_result_df.columns:
                    continue
                data = self.cal_result_df[col].dropna()
                if data.empty:
                    continue
                color = HIST_COLORS[j % len(HIST_COLORS)]
                ax.hist(data, bins=120, alpha=0.45, color=color,
                        label=f"{sig_label} (Avg: {data.mean():.2f})")
                ax.axvline(data.mean(), color=color, linewidth=1.2, linestyle="--")
                plotted = True

            ax.set_title(group_label, color=DARK, fontsize=9)
            ax.set_ylabel("Count", color=DARK, fontsize=8)
            if plotted:
                ax.legend(fontsize=7, facecolor=BG, edgecolor=DARK, labelcolor=DARK,
                          loc="upper right")
            w.style_ax(ax)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig.tight_layout()
            self._imu_hist_canvases[idx].draw()

        self._draw_axis_diagram()
        self._imu_resize_images()
