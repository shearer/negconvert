"""A dark neutral-grey theme, evoking Photoshop's darkroom-style chrome."""
from tkinter import ttk

BG = "#3a3a3a"          # app chrome background
PANEL = "#323232"       # sidebar / toolbar, slightly darker
PANEL_HOVER = "#454545"  # subtle hover for non-accent buttons
PANEL_DARK = "#282828"  # status bar, well borders
TEXT = "#e6e6e6"
TEXT_DIM = "#a3a3a3"
ACCENT = "#c9c9c9"      # bright grey accent
ACCENT_DARK = "#9a9a9a"
TROUGH = "#232323"
CANVAS_BG = "#2b2b2b"
HANDLE = "#f0f0f0"      # bright grey slider handle
HIST_BG = "#141414"     # near-black histogram background (darktable-style)


def apply(root):
    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Status.TFrame", background=PANEL_DARK)

    style.configure("TLabel", background=BG, foreground=TEXT, font=("Helvetica", 11))
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Helvetica", 11))
    style.configure("Status.TLabel", background=PANEL_DARK, foreground=TEXT_DIM, font=("Helvetica", 10))
    style.configure("Heading.TLabel", background=PANEL, foreground=TEXT,
                    font=("Helvetica", 13, "bold"))
    style.configure("Value.TLabel", background=PANEL, foreground=ACCENT,
                    font=("Helvetica", 10, "bold"))

    style.configure("TSeparator", background=PANEL_DARK)

    style.configure("TCombobox", fieldbackground=PANEL_DARK, background=PANEL_DARK,
                    foreground=TEXT, arrowcolor=TEXT, borderwidth=0, padding=6)
    style.map("TCombobox",
              fieldbackground=[("readonly", PANEL_DARK)],
              foreground=[("readonly", TEXT)],
              background=[("active", ACCENT)])
    root.option_add("*TCombobox*Listbox.background", PANEL_DARK)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#2b2b2b")

    return style
