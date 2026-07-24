import os
import tkinter as tk
import warnings

import numpy as np
from matplotlib.lines import Line2D
from PIL import Image, ImageTk

import widgets as w
from constants import BG, DARK, HIST_COLORS, WORLD_AXIS_COLOR, BOARD_AXIS_COLOR, HIST_BINS_COMPACT

_DIR = os.path.dirname(os.path.abspath(__file__))
_BIKE_IMG  = os.path.join(_DIR, "__UserFiles", "Bike_Picture.jpeg")

# Fixed signal groups — each row becomes a histogram panel
_GROUPS = [
    ("Attitude (deg)",  [("Pitch_deg",  "Pitch"), ("Roll_deg",  "Roll")]),
    ("Accel ISO (g)",   [("aFwd_g",     "Fwd"),   ("aVert_g",  "Vert"),  ("aLat_g",    "Lat")]),
    ("Gyro ISO (DPS)",  [("gPitch_DPS", "Pitch"), ("gRoll_DPS","Roll"),  ("gYaw_DPS",  "Yaw")]),
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
        right.rowconfigure(1, weight=2)   # axis diagram — 2x the bike picture's height

        # Bike picture — top, full width
        self._imu_bike_label = tk.Label(right, bg=BG)
        self._imu_bike_label.grid(row=0, column=0, sticky="nsew")

        # Axis orientation diagram — bottom, full width. set_aspect("equal") on
        # the axes (below) keeps its content square and centers it within this
        # wider figure automatically — no extra centering code needed.
        bot = tk.Frame(right, bg=BG)
        bot.grid(row=1, column=0, sticky="nsew")
        bot.columnconfigure(0, weight=1)
        bot.rowconfigure(0, weight=1)

        self._imu_axis_fig = w.make_figure(figsize=(4, 4), dpi=100)
        self._imu_axis_ax  = self._imu_axis_fig.add_subplot(111)
        self._imu_axis_ax.set_facecolor(BG)
        self._imu_axis_canvas, axis_widget = w.make_canvas(self._imu_axis_fig, bot)
        axis_widget.grid(row=0, column=0, sticky="nsew")

        self._imu_right_frame = right
        self._imu_bike_photo  = None

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
            theta_deg = 30.0
        theta = np.radians(theta_deg)

        L = 0.78   # arrow length

        # Sagittal side-view: forward = +x (right), up = +y. +Z_body points to
        # the rider's right (out of the page) and is not drawn in this 2D view.
        # Installed LSM6DSV16X board axes:
        #   +X_body = backward & θ below horizontal
        #   +Y_body = down & θ forward of straight-down
        bx = (-np.cos(theta), -np.sin(theta))
        by = ( np.sin(theta), -np.cos(theta))

        # ISO world-frame axes
        wx = (1.0, 0.0)   # forward
        wz = (0.0, 1.0)   # up

        arrow_kw = dict(head_width=0.055, head_length=0.055,
                        length_includes_head=True, zorder=3)

        # Board axes — black
        ax.arrow(0, 0, bx[0]*L, bx[1]*L, fc=BOARD_AXIS_COLOR, ec=BOARD_AXIS_COLOR, **arrow_kw)
        ax.arrow(0, 0, by[0]*L, by[1]*L, fc=BOARD_AXIS_COLOR, ec=BOARD_AXIS_COLOR, **arrow_kw)

        # World axes — blue
        ax.arrow(0, 0, wx[0]*L, wx[1]*L, fc=WORLD_AXIS_COLOR, ec=WORLD_AXIS_COLOR, **arrow_kw)
        ax.arrow(0, 0, wz[0]*L, wz[1]*L, fc=WORLD_AXIS_COLOR, ec=WORLD_AXIS_COLOR, **arrow_kw)

        # Labels — placed beyond arrow tip, anchored away from arrow body.
        # The diagram canvas is small (~15% of the window width), so fonts are
        # kept a step below the compact-subplot sizes and each text element gets
        # its own exclusive region (see the note band + legend quadrant below).
        lpad = 0.15
        # Board X: arrow goes lower-left (backward & down); label below tip
        ax.text(bx[0]*(L+lpad), bx[1]*(L+lpad), "Board X",
                color=BOARD_AXIS_COLOR, fontsize=10, ha="center", va="top", fontweight="bold")
        # Board Y: arrow goes lower-right (down & forward); label below tip
        ax.text(by[0]*(L+lpad), by[1]*(L+lpad), "Board Y",
                color=BOARD_AXIS_COLOR, fontsize=10, ha="center", va="top", fontweight="bold")
        # Fwd (X): arrow goes horizontally right; label above tip
        ax.text(wx[0]*L, wx[1]*L + 0.14, "Fwd (X)",
                color=WORLD_AXIS_COLOR, fontsize=10, ha="center", va="bottom", fontweight="bold")
        # Up (Z): arrow goes straight up; label beside the shaft at mid height —
        # the strip above the arrow tip is reserved for the legend, which is
        # wider than half the axes on the small canvas this diagram gets.
        ax.text(-0.08, 0.55, "Up (Z)",
                color=WORLD_AXIS_COLOR, fontsize=10, ha="left", va="center", fontweight="bold")
        # Out-of-plane axes note (in its own band below all arrows/labels so
        # nothing overlaps). The x-axis is mirrored (forward drawn left), so
        # out-of-page = rider's LEFT, into-page = rider's RIGHT. In ISO 8855 the
        # lateral axis is +Y (left); board +Z points the opposite way (right).
        ax.text(0.0, -1.06, "ISO 8855:  +Y → rider's left (out of page)",
                color=WORLD_AXIS_COLOR, fontsize=9, ha="center", va="center")
        ax.text(0.0, -1.22, "Board +Z → rider's right (into page)",
                color=BOARD_AXIS_COLOR, fontsize=9, ha="center", va="center")

        # Arc between straight-down (−90°) and Board Y (θ forward of down)
        arc_r = 0.28
        by_angle = np.arctan2(by[1], by[0])   # ≈ -(90° - theta)
        arc1 = np.linspace(-np.pi/2, by_angle, 40)
        ax.plot(arc_r * np.cos(arc1), arc_r * np.sin(arc1),
                color=DARK, linewidth=1.2, zorder=2)
        mid1 = (-np.pi/2 + by_angle) / 2
        ax.text(arc_r * 1.6 * np.cos(mid1), arc_r * 1.6 * np.sin(mid1),
                f"{theta_deg:.0f}°", color=DARK, fontsize=10, ha="center", va="center")

        # Arc between straight-back (−180°) and Board X (θ below horizontal)
        bx_angle = np.arctan2(bx[1], bx[0])   # ≈ -(180° - theta)
        arc2 = np.linspace(-np.pi, bx_angle, 40)
        ax.plot(arc_r * np.cos(arc2), arc_r * np.sin(arc2),
                color=DARK, linewidth=1.2, zorder=2)
        mid2 = (-np.pi + bx_angle) / 2
        ax.text(arc_r * 1.6 * np.cos(mid2), arc_r * 1.6 * np.sin(mid2),
                f"{theta_deg:.0f}°", color=DARK, fontsize=10, ha="center", va="center")

        # Dashed reference lines (horizontal + vertical)
        ax.axhline(0, color=DARK, linewidth=0.6, linestyle="--", alpha=0.35, zorder=1)
        ax.axvline(0, color=DARK, linewidth=0.6, linestyle="--", alpha=0.35, zorder=1)

        # Origin dot
        ax.plot(0, 0, "o", color=DARK, markersize=4, zorder=4)

        # Legend — screen upper-left corner: the Fwd arrow/label sit at mid
        # height, so this corner stays clear of every other text element even
        # on the small canvas this diagram renders into.
        handles = [
            Line2D([0], [0], color=BOARD_AXIS_COLOR, lw=2, label="Board frame"),
            Line2D([0], [0], color=WORLD_AXIS_COLOR, lw=2, label="ISO world frame"),
        ]
        ax.legend(handles=handles, fontsize=8, facecolor=BG, edgecolor=DARK,
                  labelcolor=DARK, loc="upper left")

        # Extra room below (-1.3) reserves an exclusive band for the Board Z note.
        lim = 1.1
        ax.set_xlim(lim, -lim)   # inverted so forward (positive x) points left
        ax.set_ylim(-1.3, lim)
        ax.set_aspect("equal")
        ax.set_title("IMU Axis Orientation — ISO 8855", color=DARK, fontsize=12)
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
        slot_h = h_px // 3   # bike picture's row is 1/3 of this frame's height (row weights 1:2)

        # Bike picture — flipped left-to-right
        try:
            img = Image.open(_BIKE_IMG)
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            img.thumbnail((slot_w, slot_h), Image.LANCZOS)
            self._imu_bike_photo = ImageTk.PhotoImage(img)
            self._imu_bike_label.configure(image=self._imu_bike_photo)
        except Exception:
            self._imu_bike_label.configure(text="[Bike_Picture.jpeg not found]",
                                           fg=DARK, font=("", 13))

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
            # Gather the group's valid signals, then bin them all on shared edges
            # (rule: 2+ histograms on one Axes share bins).
            group = []
            for j, (col, sig_label) in enumerate(signals):
                if col not in self.cal_result_df.columns:
                    continue
                data = self.cal_result_df[col].dropna()
                if data.empty:
                    continue
                group.append((j, sig_label, data))
            edges = (w.shared_bin_edges([d.values for _, _, d in group], HIST_BINS_COMPACT)
                     if group else HIST_BINS_COMPACT)
            for j, sig_label, data in group:
                color = HIST_COLORS[j % len(HIST_COLORS)]
                w.plot_hist_line(ax, data, edges, color=color,
                                 label=f"{sig_label} (Avg: {data.mean():.2f})")
                ax.axvline(data.mean(), color=color, linewidth=1.2, linestyle="--")
                plotted = True

            ax.set_title(group_label, color=DARK, fontsize=13)
            ax.set_ylabel("Count", color=DARK, fontsize=12)
            if plotted:
                ax.legend(fontsize=10, facecolor=BG, edgecolor=DARK, labelcolor=DARK,
                          loc="upper right")
            w.style_ax(ax)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig.tight_layout()
            self._imu_hist_canvases[idx].draw()

        self._draw_axis_diagram()
        self._imu_resize_images()
