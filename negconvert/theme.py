"""Dark neutral-grey theme colors and Qt stylesheet."""

BG = "#3a3a3a"
PANEL = "#323232"
PANEL_HOVER = "#454545"
PANEL_DARK = "#282828"
TEXT = "#e6e6e6"
TEXT_DIM = "#a3a3a3"
ACCENT = "#c9c9c9"
ACCENT_DARK = "#9a9a9a"
TROUGH = "#232323"
CANVAS_BG = "#2b2b2b"
HANDLE = "#f0f0f0"
HIST_BG = "#141414"


def stylesheet():
    return f"""
    QWidget {{
        background-color: {BG};
        color: {TEXT};
        font-family: Helvetica;
        font-size: 11px;
    }}
    QMainWindow {{
        background-color: {BG};
    }}
    QStatusBar {{
        background-color: {PANEL_DARK};
        color: {TEXT_DIM};
        font-size: 10px;
    }}
    QStatusBar QLabel {{
        background-color: {PANEL_DARK};
        color: {TEXT_DIM};
        font-size: 10px;
        padding: 2px 6px;
    }}
    QComboBox {{
        background-color: {PANEL_DARK};
        color: {TEXT};
        border: none;
        padding: 6px 8px;
        border-radius: 4px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        color: {TEXT};
    }}
    QComboBox QAbstractItemView {{
        background-color: {PANEL_DARK};
        color: {TEXT};
        selection-background-color: {ACCENT};
        selection-color: #2b2b2b;
        border: none;
        outline: none;
    }}
    QScrollBar:horizontal {{
        background: {PANEL_DARK};
        height: 8px;
        border-radius: 4px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {ACCENT_DARK};
        border-radius: 4px;
        min-width: 20px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
    QScrollBar:vertical {{
        background: {PANEL_DARK};
        width: 8px;
        border-radius: 4px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {ACCENT_DARK};
        border-radius: 4px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QMenu {{
        background-color: {PANEL_DARK};
        color: {TEXT};
        border: 1px solid {PANEL_HOVER};
    }}
    QMenu::item:selected {{
        background-color: {ACCENT};
        color: #2b2b2b;
    }}
    QToolTip {{
        background-color: {PANEL_DARK};
        color: {TEXT};
        border: 1px solid {PANEL_HOVER};
    }}
    """
