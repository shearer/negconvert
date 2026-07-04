"""A neutral middle-grey ttk theme, evoking a darkroom / grey card look."""
from tkinter import ttk

BG = "#808080"          # middle grey (18% grey card reference)
PANEL = "#6e6e6e"       # sidebar / toolbar, slightly darker
PANEL_DARK = "#5a5a5a"  # status bar, well borders
TEXT = "#f2f2f2"
TEXT_DIM = "#d0d0d0"
ACCENT = "#e8a33d"      # amber safelight accent
ACCENT_DARK = "#c9862a"
TROUGH = "#4d4d4d"
CANVAS_BG = "#3a3a3a"


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
                    font=("Helvetica", 12, "bold"))
    style.configure("Value.TLabel", background=PANEL, foreground=ACCENT,
                    font=("Helvetica", 10, "bold"))

    style.configure("TButton", background=PANEL_DARK, foreground=TEXT,
                    font=("Helvetica", 10), borderwidth=0, focusthickness=0,
                    padding=(10, 6))
    style.map("TButton",
              background=[("active", ACCENT), ("pressed", ACCENT_DARK)],
              foreground=[("active", "#2b2b2b")])

    style.configure("Accent.TButton", background=ACCENT_DARK, foreground="#2b2b2b",
                     font=("Helvetica", 10, "bold"), borderwidth=0, padding=(10, 6))
    style.map("Accent.TButton",
              background=[("active", ACCENT), ("pressed", ACCENT_DARK)])

    style.configure("Horizontal.TScale", background=PANEL, troughcolor=TROUGH,
                    sliderthickness=16, borderwidth=0)
    style.map("Horizontal.TScale", background=[("active", PANEL)])

    style.configure("TSeparator", background=PANEL_DARK)

    return style
