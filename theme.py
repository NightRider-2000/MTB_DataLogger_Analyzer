import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from constants import (BG, DARK, FIELD, BTN_FG, TABLE_GRID,
                       FONT_SCALE, FONT_DELTA)

# Keep references to Tk objects created in setup_theme — Tk holds only weak
# links, and tkinter deletes them on garbage collection (Font.__del__ removes
# the named font; a collected PhotoImage blanks the gridline element).
_gridline_img = None
_table_font   = None


def _scale_named_fonts(root):
    """Scale every Tk named font by FONT_SCALE (+FONT_DELTA) so all default-font
    UI text follows the global size."""
    for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
                 "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
                 "TkIconFont", "TkTooltipFont"):
        try:
            f = tkfont.nametofont(name, root=root)
            size = f.cget("size")
            if size:
                f.configure(size=int(round(size * FONT_SCALE)) + FONT_DELTA)
        except Exception:
            pass


def setup_theme(root):
    _scale_named_fonts(root)
    s = ttk.Style(root)
    s.theme_use("clam")

    # Default-font size after global FONT_SCALE has been applied above.
    _default = tkfont.nametofont("TkDefaultFont", root=root)
    _default_size = _default.cget("size")
    # Tab labels and Device-tab buttons read ~30% smaller than the scaled default.
    _tab_font = ("TkDefaultFont", int(round(_default_size * 0.7)))
    _small_btn_font = ("TkDefaultFont", int(round(_default_size * 0.7)))
    # Named font for ALL tables (Treeview body + headings + the Device-tab
    # config grid): 2 pt smaller than the scaled default. Widgets reference it
    # by name ("TableFont"); the module-level ref keeps it from being GC'd
    # (Font.__del__ deletes the named font).
    global _table_font
    _table_font = tkfont.Font(root=root, name="TableFont",
                              family=_default.cget("family"),
                              size=_default_size - 2)
    table_font = _table_font

    s.configure("Dark.TButton",
                background=DARK, foreground=BTN_FG,
                borderwidth=0, focusthickness=0, relief="flat", padding=[8, 4])
    s.map("Dark.TButton",
          background=[("active", "#2a5298"), ("disabled", FIELD)],
          foreground=[("active", BTN_FG)])

    # Compact button variant (Device tab): smaller font + tighter padding so the
    # full SD-file button row (incl. Delete Selected) fits on screen.
    s.configure("Small.TButton",
                background=DARK, foreground=BTN_FG, font=_small_btn_font,
                borderwidth=0, focusthickness=0, relief="flat", padding=[4, 2])
    s.map("Small.TButton",
          background=[("active", "#2a5298"), ("disabled", FIELD)],
          foreground=[("active", BTN_FG)])

    s.configure("App.TNotebook", background=BG, borderwidth=0)
    s.configure("App.TNotebook.Tab",
                background=FIELD, foreground=DARK, font=_tab_font, padding=[7, 3])
    s.map("App.TNotebook.Tab",
          background=[("selected", DARK)],
          foreground=[("selected", BTN_FG)])

    s.configure("TCombobox",
                fieldbackground=FIELD, background=DARK, foreground=DARK,
                selectbackground=DARK, selectforeground=BTN_FG, arrowcolor=BTN_FG)
    root.option_add("*TCombobox*Listbox.background",       FIELD)
    root.option_add("*TCombobox*Listbox.foreground",       DARK)
    root.option_add("*TCombobox*Listbox.selectBackground", DARK)
    root.option_add("*TCombobox*Listbox.selectForeground", BTN_FG)

    s.configure("Treeview",
                background=FIELD, fieldbackground=FIELD,
                foreground=DARK, font=table_font,
                rowheight=table_font.metrics("linespace") + 8)
    s.configure("Treeview.Heading",
                background=DARK, foreground=BTN_FG, relief="flat",
                font=table_font)
    s.map("Treeview",
          background=[("selected", DARK)],
          foreground=[("selected", BTN_FG)])
    s.map("Treeview.Heading", background=[("active", DARK)])
    s.configure("TScrollbar", background=FIELD, troughcolor=BG, borderwidth=0)

    _setup_table_gridlines(root, s)


def _setup_table_gridlines(root, s):
    """RULE: every table (ttk.Treeview) shows solid grey gridlines around every
    cell (requires Tk 9). Two halves:
      - horizontal: a 1-px TABLE_GRID-colored image element appended to the bottom of
        the shared Row layout, so every row of every treeview draws a bottom
        rule (tag/selection backgrounds keep working — the line draws on top);
      - vertical: Tk 9 native column separators, colored via the
        Treeitem.separator element. Each table opts its columns in through
        widgets.enable_gridlines(tree).
    """
    global _gridline_img
    try:
        _gridline_img = tk.PhotoImage(master=root, width=1, height=1)
        _gridline_img.put(TABLE_GRID, to=(0, 0, 1, 1))
        s.element_create("Gridline.hline", "image", _gridline_img, sticky="we")
        s.layout("Row", [
            ("Treeitem.row", {"sticky": "nswe", "children": [
                ("Gridline.hline", {"side": "bottom", "sticky": "we"}),
            ]}),
        ])
        # Column separators (vertical lines) — solid grey, 1 px.
        s.configure("Separator", background=TABLE_GRID)
        s.configure("Treeview", columnseparatorwidth=1)
    except tk.TclError:
        pass   # pre-9 Tk: no gridline support; tables render as before
