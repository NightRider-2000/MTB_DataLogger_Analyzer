from tkinter import ttk

from constants import BG, DARK, FIELD, BTN_FG


def setup_theme(root):
    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure("Dark.TButton",
                background=DARK, foreground=BTN_FG,
                borderwidth=0, focusthickness=0, relief="flat", padding=[8, 4])
    s.map("Dark.TButton",
          background=[("active", "#2a5298"), ("disabled", FIELD)],
          foreground=[("active", BTN_FG)])

    s.configure("App.TNotebook", background=BG, borderwidth=0)
    s.configure("App.TNotebook.Tab",
                background=FIELD, foreground=DARK, padding=[10, 4])
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
                foreground=DARK, rowheight=22)
    s.configure("Treeview.Heading",
                background=DARK, foreground=BTN_FG, relief="flat")
    s.map("Treeview",
          background=[("selected", DARK)],
          foreground=[("selected", BTN_FG)])
    s.map("Treeview.Heading", background=[("active", DARK)])
    s.configure("TScrollbar", background=FIELD, troughcolor=BG, borderwidth=0)
