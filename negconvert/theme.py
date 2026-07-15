"""Dark neutral-grey theme colors and Qt stylesheet."""

BG = "#3a3a3a"
PANEL = "#323232"
PANEL_HOVER = "#454545"
PANEL_DARK = "#282828"
INPUT_BG = "#242424"        # slightly darker than panel for inputs
INPUT_BORDER = "#484848"    # subtle border around inputs
INPUT_BORDER_HOVER = "#686868"
TEXT = "#e6e6e6"
TEXT_DIM = "#888888"
TEXT_LABEL = "#b0b0b0"      # dimmer than body text for secondary labels
ACCENT = "#c9c9c9"
ACCENT_DARK = "#9a9a9a"
TROUGH = "#1e1e1e"
TROUGH_FILLED = "#a8a8a8"   # filled portion of slider track
CANVAS_BG = "#2b2b2b"
HANDLE = "#ffffff"
HANDLE_BORDER = "#888888"
HIST_BG = "#141414"


def stylesheet():
    return f"""
    QWidget {{
        background-color: {BG};
        color: {TEXT};
        font-family: ".AppleSystemUIFont", "Helvetica Neue", Helvetica, Arial, sans-serif;
        font-size: 12px;
    }}
    QMainWindow {{
        background-color: {BG};
    }}
    QStatusBar {{
        background-color: {PANEL_DARK};
        color: {TEXT_DIM};
        font-size: 11px;
        border-top: 1px solid #202020;
    }}
    QStatusBar QLabel {{
        background-color: {PANEL_DARK};
        color: {TEXT_DIM};
        font-size: 11px;
        padding: 3px 8px;
    }}

    /* ── Dropdowns ── */
    QComboBox {{
        background-color: {INPUT_BG};
        color: {TEXT};
        border: 1px solid {INPUT_BORDER};
        border-radius: 6px;
        padding: 5px 32px 5px 10px;
        min-height: 28px;
        selection-background-color: {PANEL_HOVER};
    }}
    QComboBox:hover {{
        border-color: {INPUT_BORDER_HOVER};
    }}
    QComboBox:focus {{
        border-color: {ACCENT_DARK};
        outline: none;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 28px;
        border: none;
        border-left: 1px solid {INPUT_BORDER};
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
        background: transparent;
    }}
    QComboBox::down-arrow {{
        width: 10px;
        height: 10px;
        image: none;
        border-left:  4px solid transparent;
        border-right: 4px solid transparent;
        border-top:   5px solid {TEXT_DIM};
    }}
    QComboBox QAbstractItemView {{
        background-color: {INPUT_BG};
        color: {TEXT};
        selection-background-color: {PANEL_HOVER};
        selection-color: {TEXT};
        border: 1px solid {INPUT_BORDER};
        border-radius: 6px;
        padding: 3px;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 5px 10px;
        border-radius: 4px;
        min-height: 24px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {PANEL_HOVER};
        color: {TEXT};
    }}

    /* ── Scrollbars ── */
    QScrollBar:horizontal {{
        background: transparent;
        height: 6px;
        border-radius: 3px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {INPUT_BORDER};
        border-radius: 3px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT_DARK};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        border-radius: 3px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {INPUT_BORDER};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {ACCENT_DARK};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    /* ── Menus ── */
    QMenu {{
        background-color: {INPUT_BG};
        color: {TEXT};
        border: 1px solid {INPUT_BORDER};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 14px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {ACCENT};
        color: #1a1a1a;
    }}
    QToolTip {{
        background-color: {INPUT_BG};
        color: {TEXT};
        border: 1px solid {INPUT_BORDER};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    """
