"""A neutral middle-grey theme, evoking a darkroom / grey card look."""
from tkinter import ttk

BG = "#7d7d7d"          # middle grey (18% grey card reference)
PANEL = "#6b6b6b"       # sidebar / toolbar, slightly darker
PANEL_HOVER = "#787878"  # subtle hover for non-accent buttons
PANEL_DARK = "#575757"  # status bar, well borders
TEXT = "#f5f5f5"
TEXT_DIM = "#cfcfcf"
ACCENT = "#d6d6d6"      # bright grey accent
ACCENT_DARK = "#b0b0b0"
TROUGH = "#4a4a4a"
CANVAS_BG = "#383838"
HANDLE = "#f2f2f2"      # bright grey slider handle


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
