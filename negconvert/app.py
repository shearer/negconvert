"""PySide6 UI for NegConvert."""
import os

import numpy as np
from PIL import Image

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QComboBox, QSizePolicy, QMenu, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath,
    QPixmap, QImage, QFont, QIcon, QKeySequence, QShortcut,
)

from . import crop
from . import processor
from . import theme
from .widgets import (
    ColorSwatch, Filmstrip, Histogram, ModernSlider,
    PillButton, PipetteButton, TabBar, numpy_to_pixmap,
)

PREVIEW_MAX_DIM = 900
HANDLE_HIT_RADIUS = 12
CROP_HANDLE_R = 8
TAB_COLORS, TAB_ADJUST, TAB_CROP, TAB_EXPORT = 0, 1, 2, 3
STRAIGHTEN_GUIDE_COUNT = 10
STRAIGHTEN_GUIDE_COLOR = "#ff3b30"

# Double-click cycles through these; None means fit-to-window.
ZOOM_LEVELS = (None, 0.5, 1.0)

FRAME_COLORS = [("White", "#ffffff"), ("Middle Grey", "#808080"), ("Dark Grey", "#333333")]
FRAME_BORDER_COLOR = "#555555"
DEFAULT_FRAME_COLOR = "#808080"
IMAGE_FIT_SCALE = 0.9


class PhotoItem:
    def __init__(self, path):
        self.path = path
        self.full_arr = None
        self.preview_arr = None
        self.is_linear = False
        self.loaded = False
        self.params = processor.Params()
        self.crop_rect = crop.FULL_RECT
        self.aspect_ratio = None
        self.rotation_90 = 0
        self.straighten_angle = 0.0
        self.auto_baseline = (0.0, 1.0, 1.0)


class ImageCanvas(QWidget):
    """The main preview area: draws the image and crop overlay via paintEvent."""
    mouse_press = Signal(float, float)
    mouse_drag = Signal(float, float)
    mouse_release = Signal()
    double_click = Signal(float, float)
    right_click = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(DEFAULT_FRAME_COLOR)
        self._pixmap = None
        self._img_offset = (0, 0)
        self._overlay = None
        self.setMouseTracking(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_bg_color(self, color_str):
        self._bg_color = QColor(color_str)
        self.update()

    def set_image(self, pixmap, ox, oy):
        self._pixmap = pixmap
        self._img_offset = (ox, oy)
        self.update()

    def clear_image(self):
        self._pixmap = None
        self._overlay = None
        self.update()

    def set_overlay(self, overlay_dict):
        self._overlay = overlay_dict
        self.update()

    def clear_overlay(self):
        self._overlay = None
        self.update()

    def set_cursor_crosshair(self, active):
        self.setCursor(Qt.CursorShape.CrossCursor if active else Qt.CursorShape.ArrowCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self._bg_color)

        if self._pixmap is None:
            color = "#2b2b2b" if self._bg_color == QColor("#ffffff") else QColor(theme.TEXT_DIM)
            painter.setPen(QColor(color) if isinstance(color, str) else color)
            painter.setFont(QFont("Helvetica", 13))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "Open a negative scan (or a folder of them) to begin\n"
                "(click the image later to sample the film base color)",
            )
            return

        ox, oy = self._img_offset
        painter.drawPixmap(ox, oy, self._pixmap)
        painter.setPen(QPen(QColor(FRAME_BORDER_COLOR), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(ox, oy, self._pixmap.width(), self._pixmap.height())

        if self._overlay:
            self._draw_overlay(painter)

    def _draw_overlay(self, painter):
        o = self._overlay
        bg = QColor(o["bg_color"])
        ix0, iy0, ix1, iy1 = (int(v) for v in o["image_rect"])
        cx0, cy0, cx1, cy1 = (int(v) for v in o["crop_rect"])

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRect(QRect(ix0, iy0, ix1 - ix0, cy0 - iy0))
        painter.drawRect(QRect(ix0, cy1, ix1 - ix0, iy1 - cy1))
        painter.drawRect(QRect(ix0, cy0, cx0 - ix0, cy1 - cy0))
        painter.drawRect(QRect(cx1, cy0, ix1 - cx1, cy1 - cy0))

        painter.setPen(QPen(QColor(theme.ACCENT), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRect(cx0, cy0, cx1 - cx0, cy1 - cy0))

        r = CROP_HANDLE_R
        painter.setPen(QPen(QColor(theme.ACCENT_DARK), 2))
        painter.setBrush(QBrush(QColor(theme.HANDLE)))
        for hx, hy in o["handles"].values():
            painter.drawEllipse(int(hx - r), int(hy - r), r * 2, r * 2)

        if o.get("show_guides"):
            pen = QPen(QColor(STRAIGHTEN_GUIDE_COLOR), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            for i in range(1, STRAIGHTEN_GUIDE_COUNT + 1):
                gy = iy0 + (i / (STRAIGHTEN_GUIDE_COUNT + 1)) * (iy1 - iy0)
                painter.drawLine(ix0, int(gy), ix1, int(gy))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press.emit(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.mouse_drag.emit(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_release.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_click.emit(event.position().x(), event.position().y())

    def contextMenuEvent(self, event):
        self.right_click.emit(event.globalPos())


def _input_label_style():
    return (f"color: {theme.TEXT_DIM}; background: {theme.PANEL}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 0.6px; "
            f"text-transform: uppercase; padding-top: 4px;")


def _separator(parent):
    sep = QFrame(parent)
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {theme.PANEL_DARK}; background: {theme.PANEL_DARK}; max-height: 1px;")
    return sep


def _film_base_hint(mode):
    if mode == "E-6":
        return ("Click the pipette, then click a clear\n"
                 "(unexposed) edge of the slide to correct\n"
                 "for any color cast.")
    return ("Click the pipette, then click anywhere on\n"
             "the image to sample the orange mask from\n"
             "unexposed film.")


class NegConvertApp(QMainWindow):
    EXPORT_FORMATS = [("TIFF", "tif"), ("PNG", "png"), ("JPEG", "jpg"), ("Linear DNG", "dng")]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NegConvert — Negative & Slide Converter")
        self.resize(1280, 820)
        self.setStyleSheet(theme.stylesheet())
        self._set_window_icon()

        self.params = processor.Params()
        self.full_arr = None
        self.preview_arr = None
        self.is_linear = False
        self.image_path = None
        self.frame_bg_color = DEFAULT_FRAME_COLOR

        self.crop_mode = False
        self.crop_rect = crop.FULL_RECT
        self.aspect_ratio = None
        self.rotation_90 = 0
        self.straighten_angle = 0.0
        self._working_arr = None
        self._show_straighten_guides = False
        self._crop_drag = None
        self._crop_handles = {}
        self._crop_rect_canvas = None

        self._zoom_index = 0  # index into ZOOM_LEVELS
        self._zoom_center = (0.5, 0.5)
        self._zoom_window_origin = (0, 0)
        self._zoom_full_dims = (1, 1)
        self._sample_arr = None
        self._img_offset = (0, 0)
        self._img_display_scale = 1.0
        self._display_origin_px = (0, 0)
        self.pipette_active = False

        self.photos = []
        self.current_photo_index = -1

        self._build_layout()
        self._bind_shortcuts()

    def _set_window_icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon_1024.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    # ---------- layout ----------

    def _build_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background: {theme.PANEL};")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(12, 8, 12, 8)
        tl.setSpacing(4)
        for text, cmd in [
            ("Open Negative…", self.open_image),
            ("Open Folder…", self.open_folder),
            ("Auto Base Color", self.auto_base),
            ("Reset Adjustments", self.reset_adjustments),
        ]:
            btn = PillButton(toolbar, text, command=cmd, bg=theme.PANEL)
            tl.addWidget(btn)
        tl.addStretch()
        main_layout.addWidget(toolbar)

        # Body: canvas + sidebar
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        canvas_wrap = QWidget()
        canvas_wrap.setStyleSheet(f"background: {theme.BG};")
        cw_layout = QVBoxLayout(canvas_wrap)
        cw_layout.setContentsMargins(10, 10, 10, 10)
        self.image_canvas = ImageCanvas()
        self.image_canvas.mouse_press.connect(self.on_canvas_press)
        self.image_canvas.mouse_drag.connect(self.on_canvas_drag)
        self.image_canvas.mouse_release.connect(self.on_canvas_release)
        self.image_canvas.double_click.connect(self.on_canvas_double_click)
        self.image_canvas.right_click.connect(self._show_frame_menu)
        cw_layout.addWidget(self.image_canvas)
        body_layout.addWidget(canvas_wrap, stretch=1)

        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar)
        main_layout.addWidget(body, stretch=1)

        # Filmstrip
        self.filmstrip = Filmstrip(central, on_select=self._select_photo,
                                   on_mark_change=self._on_marks_changed)
        main_layout.addWidget(self.filmstrip)

        # Status bar
        self.status_lbl = QLabel("No image loaded")
        self.statusBar().addWidget(self.status_lbl)
        self.statusBar().setStyleSheet(
            f"background: {theme.PANEL_DARK}; color: {theme.TEXT_DIM}; font-size: 10px;"
        )

    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setFixedWidth(384)
        sidebar.setStyleSheet(f"background: {theme.PANEL};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.setSpacing(0)

        heading = QLabel("Histogram")
        heading.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL}; padding-bottom: 6px;")
        sl.addWidget(heading)

        self.histogram = Histogram(sidebar, height=120)
        sl.addWidget(self.histogram)
        sl.addSpacing(10)

        sl.addWidget(_separator(sidebar))
        sl.addSpacing(10)

        self.tab_bar = TabBar(sidebar, ["Colors", "Adjustments", "Crop", "Export"],
                              on_change=self.on_tab_changed, active=TAB_COLORS)
        sl.addWidget(self.tab_bar)
        sl.addSpacing(10)

        self._tab_stack = QStackedWidget(sidebar)
        self._tab_stack.setStyleSheet(f"background: {theme.PANEL};")
        sl.addWidget(self._tab_stack, stretch=1)

        adjust_tab = QWidget()
        adjust_tab.setStyleSheet(f"background: {theme.PANEL};")
        colors_tab = QWidget()
        colors_tab.setStyleSheet(f"background: {theme.PANEL};")
        crop_tab = QWidget()
        crop_tab.setStyleSheet(f"background: {theme.PANEL};")
        export_tab = QWidget()
        export_tab.setStyleSheet(f"background: {theme.PANEL};")

        self._build_adjustments_tab(adjust_tab)
        self._build_colors_tab(colors_tab)
        self._build_crop_tab(crop_tab)
        self._build_export_tab(export_tab)

        for w in (colors_tab, adjust_tab, crop_tab, export_tab):
            self._tab_stack.addWidget(w)
        self._tab_stack.setCurrentIndex(TAB_COLORS)

        return sidebar

    def _build_adjustments_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        sliders = [
            ("exposure_s",        "Exposure (EV)",      -8.0,  8.0,  self.params.exposure,        0.0),
            ("density_s",         "Density",            -4.0,  4.0,  self.params.density,          0.0),
            ("shadow_density_s",  "Shadow Density",     -2.0,  2.0,  self.params.shadow_density,   0.0),
            ("highlight_density_s","Highlight Density", -2.0,  2.0,  self.params.highlight_density,0.0),
            ("contrast_s",        "Contrast",            0.5,  2.5,  self.params.contrast,          1.0),
            ("gamma_s",           "Gamma",               0.3,  2.5,  self.params.gamma,             1.0),
            ("saturation_s",      "Saturation",          0.0,  2.0,  self.params.saturation,        1.0),
            ("denoise_s",         "Denoise",             0.0,  2.0,  self.params.denoise,           0.0),
            ("sharpen_s",         "Sharpening",          0.0,  2.0,  self.params.sharpen,           0.0),
        ]
        for attr, label, frm, to, initial, default in sliders:
            s = ModernSlider(parent, label, frm, to, initial, self.on_slider,
                             bg=theme.PANEL, default=default)
            setattr(self, attr, s)
            layout.addWidget(s)
        layout.addStretch()

    def _build_colors_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        lbl_mode = QLabel("Film Type")
        lbl_mode.setStyleSheet(_input_label_style())
        layout.addWidget(lbl_mode)

        self.mode_combo = QComboBox(parent)
        for m in processor.FILM_MODES:
            self.mode_combo.addItem(m)
        self.mode_combo.setCurrentIndex(processor.FILM_MODES.index(self.params.mode))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
        layout.addWidget(self.mode_combo)

        layout.addSpacing(4)
        layout.addWidget(_separator(parent))
        layout.addSpacing(4)

        self.color_balance_section = QWidget(parent)
        self.color_balance_section.setStyleSheet(f"background: {theme.PANEL};")
        cb_layout = QVBoxLayout(self.color_balance_section)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setSpacing(2)

        h = QLabel("Color Balance")
        h.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL};")
        cb_layout.addWidget(h)

        for attr, label, default in [
            ("shift_r_s", "Red",   0.0),
            ("shift_g_s", "Green", 0.0),
            ("shift_b_s", "Blue",  0.0),
        ]:
            s = ModernSlider(self.color_balance_section, label, -0.5, 0.5, 0.0, self.on_slider,
                             bg=theme.PANEL, default=default)
            setattr(self, attr, s)
            cb_layout.addWidget(s)

        layout.addWidget(self.color_balance_section)

        layout.addSpacing(4)
        layout.addWidget(_separator(parent))
        layout.addSpacing(4)

        self.film_base_section = QWidget(parent)
        self.film_base_section.setStyleSheet(f"background: {theme.PANEL};")
        fb_layout = QVBoxLayout(self.film_base_section)
        fb_layout.setContentsMargins(0, 0, 0, 0)
        fb_layout.setSpacing(2)

        h2 = QLabel("Film Base")
        h2.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL};")
        fb_layout.addWidget(h2)

        swatch_row = QWidget(self.film_base_section)
        swatch_row.setStyleSheet(f"background: {theme.PANEL};")
        sr_layout = QHBoxLayout(swatch_row)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        sr_layout.setSpacing(8)

        self.pipette_btn = PipetteButton(swatch_row, command=self._on_pipette_toggle, bg=theme.PANEL)
        sr_layout.addWidget(self.pipette_btn)

        self.base_swatch = ColorSwatch(32, swatch_row)
        sr_layout.addWidget(self.base_swatch)

        self.base_lbl = QLabel("not sampled", swatch_row)
        self.base_lbl.setStyleSheet(f"color: {theme.TEXT}; background: {theme.PANEL}; font-size: 11px;")
        sr_layout.addWidget(self.base_lbl)
        sr_layout.addStretch()
        fb_layout.addWidget(swatch_row)

        self.base_hint_lbl = QLabel(_film_base_hint(self.params.mode))
        self.base_hint_lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; background: {theme.PANEL}; font-size: 11px; line-height: 1.5;")
        fb_layout.addWidget(self.base_hint_lbl)

        layout.addWidget(self.film_base_section)
        layout.addStretch()

        self._update_mode_ui(self.params.mode)
        self._update_base_swatch()

    def _build_crop_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        h = QLabel("Crop")
        h.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL};")
        layout.addWidget(h)

        lbl_aspect = QLabel("Aspect Ratio")
        lbl_aspect.setStyleSheet(_input_label_style())
        layout.addWidget(lbl_aspect)
        self.aspect_combo = QComboBox(parent)
        for label, _ in crop.ASPECT_PRESETS:
            self.aspect_combo.addItem(label)
        self.aspect_combo.currentIndexChanged.connect(lambda _: self.on_aspect_change())
        layout.addWidget(self.aspect_combo)

        crop_btn_row = QWidget(parent)
        crop_btn_row.setStyleSheet(f"background: {theme.PANEL};")
        cbr = QHBoxLayout(crop_btn_row)
        cbr.setContentsMargins(0, 0, 0, 0)
        cbr.setSpacing(6)
        cbr.addWidget(PillButton(crop_btn_row, "Apply Crop", command=self.apply_crop, bg=theme.PANEL))
        cbr.addWidget(PillButton(crop_btn_row, "Reset Crop", command=self.reset_crop, bg=theme.PANEL))
        layout.addWidget(crop_btn_row)

        hint = QLabel("While this tab is open, drag the corner\n"
                       "handles or the box itself on the image.\n"
                       "Switch tabs to preview the cropped result.")
        hint.setStyleSheet(f"color: {theme.TEXT_DIM}; background: {theme.PANEL}; font-size: 11px; line-height: 1.5;")
        layout.addWidget(hint)

        layout.addWidget(_separator(parent))

        h2 = QLabel("Rotate")
        h2.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL};")
        layout.addWidget(h2)

        rotate_row = QWidget(parent)
        rotate_row.setStyleSheet(f"background: {theme.PANEL};")
        rr = QHBoxLayout(rotate_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(6)
        rr.addWidget(PillButton(rotate_row, "Rotate Left", command=self.rotate_left, bg=theme.PANEL))
        rr.addWidget(PillButton(rotate_row, "Rotate Right", command=self.rotate_right, bg=theme.PANEL))
        rr.addStretch()
        layout.addWidget(rotate_row)

        self.straighten_s = ModernSlider(parent, "Straighten (°)", -45.0, 45.0,
                                          self.straighten_angle, self.on_straighten_change,
                                          bg=theme.PANEL, default=0.0)
        self.straighten_s.track_pressed.connect(self._on_straighten_drag_start)
        self.straighten_s.track_released.connect(self._on_straighten_drag_end)
        layout.addWidget(self.straighten_s)
        layout.addStretch()

    def _build_export_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        h = QLabel("Export")
        h.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL};")
        layout.addWidget(h)

        desc = QLabel("Save the converted positive - with any\n"
                       "crop currently set - as DNG, TIFF, PNG, or JPEG.")
        desc.setStyleSheet(f"color: {theme.TEXT_DIM}; background: {theme.PANEL}; font-size: 11px; line-height: 1.5;")
        layout.addWidget(desc)

        lbl_format = QLabel("Format")
        lbl_format.setStyleSheet(_input_label_style())
        layout.addWidget(lbl_format)
        self.format_combo = QComboBox(parent)
        for label, _ in self.EXPORT_FORMATS:
            self.format_combo.addItem(label)
        self.format_combo.currentIndexChanged.connect(lambda _: self._on_export_format_change())
        layout.addWidget(self.format_combo)

        lbl_profile = QLabel("Color Profile")
        lbl_profile.setStyleSheet(_input_label_style())
        layout.addWidget(lbl_profile)
        self.profile_combo = QComboBox(parent)
        for p in processor.COLOR_PROFILES:
            self.profile_combo.addItem(p)
        layout.addWidget(self.profile_combo)

        self.profile_hint_lbl = QLabel("")
        self.profile_hint_lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; background: {theme.PANEL}; font-size: 10px;")
        layout.addWidget(self.profile_hint_lbl)

        save_btn = PillButton(parent, "Save As…", command=self.save_image,
                              accent=True, font=("Helvetica", 11, "bold"))
        layout.addWidget(save_btn)

        layout.addWidget(_separator(parent))

        h2 = QLabel("Batch Export")
        h2.setStyleSheet(f"color: {theme.TEXT}; font-size: 11px; font-weight: bold; letter-spacing: 0.8px; text-transform: uppercase; background: {theme.PANEL};")
        layout.addWidget(h2)

        self.marked_lbl = QLabel("Ctrl+click photos in the filmstrip\nto select several for batch export.")
        self.marked_lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; background: {theme.PANEL}; font-size: 11px; line-height: 1.5;")
        layout.addWidget(self.marked_lbl)

        layout.addWidget(PillButton(parent, "Export Selected…", command=self.export_selected, bg=theme.PANEL))
        layout.addStretch()

    def _bind_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Open, self, self.open_image)
        QShortcut(QKeySequence.StandardKey.Save, self, self.save_image)

    # ---------- image IO ----------

    def open_image(self):
        raw_patterns = " ".join(f"*{ext}" for ext in sorted(processor.RAW_EXTENSIONS))
        image_patterns = " ".join(f"*{ext}" for ext in sorted(processor.IMAGE_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open negative or slide scan", "",
            f"All supported ({image_patterns});;"
            f"Scanner/Camera RAW ({raw_patterns});;"
            "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp);;"
            "All files (*.*)"
        )
        if path:
            self._load_photo_list([path])

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open folder of negative scans")
        if not folder:
            return
        paths = sorted(
            os.path.join(folder, name) for name in os.listdir(folder)
            if os.path.splitext(name)[1].lower() in processor.IMAGE_EXTENSIONS
        )
        if not paths:
            QMessageBox.information(self, "No images found",
                                    "That folder has no supported image files "
                                    "(JPG/PNG/TIFF/BMP, or a scanner/camera RAW format).")
            return
        self._load_photo_list(paths)

    def _load_photo_list(self, paths):
        self.photos = [PhotoItem(p) for p in paths]
        self.current_photo_index = -1
        thumbs = [(item.path, processor.extract_thumbnail(item.path)) for item in self.photos]
        self.filmstrip.set_photos(thumbs)
        self._select_photo(0)

    def _select_photo(self, index):
        if not (0 <= index < len(self.photos)) or index == self.current_photo_index:
            return

        if 0 <= self.current_photo_index < len(self.photos):
            outgoing = self.photos[self.current_photo_index]
            outgoing.params = self.params
            outgoing.crop_rect = self.crop_rect
            outgoing.aspect_ratio = self.aspect_ratio
            outgoing.rotation_90 = self.rotation_90
            outgoing.straighten_angle = self.straighten_angle

        item = self.photos[index]
        if not self._ensure_photo_loaded(item):
            return

        self.current_photo_index = index
        self.full_arr = item.full_arr
        self.preview_arr = item.preview_arr
        self.is_linear = item.is_linear
        self.image_path = item.path
        self.params = item.params
        self.crop_rect = item.crop_rect
        self.aspect_ratio = item.aspect_ratio
        self.rotation_90 = item.rotation_90
        self.straighten_angle = item.straighten_angle

        self.crop_mode = False
        self.tab_bar.select(TAB_COLORS)
        self._tab_stack.setCurrentIndex(TAB_COLORS)

        self._sync_controls_from_state(item)
        self.filmstrip.set_selected(index)

        h, w = self.full_arr.shape[:2]
        total = len(self.photos)
        label = (os.path.basename(item.path) if total == 1
                 else f"{os.path.basename(item.path)} ({index + 1}/{total})")
        self.status_lbl.setText(f"{label}  —  {w}×{h}px")

        self.render_preview()

    def _ensure_photo_loaded(self, item):
        if item.loaded:
            return True
        try:
            item.full_arr, item.is_linear = processor.load_negative(item.path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open image",
                                 f"{os.path.basename(item.path)}: {exc}")
            return False
        item.preview_arr = processor.downscale(item.full_arr, PREVIEW_MAX_DIM, item.is_linear)
        item.params.base_color = processor.estimate_base_color(item.preview_arr)
        exposure, contrast, gamma = processor.auto_levels(
            item.preview_arr, item.params.base_color, item.is_linear)
        item.params.exposure, item.params.contrast, item.params.gamma = exposure, contrast, gamma
        item.auto_baseline = (exposure, contrast, gamma)
        item.loaded = True
        return True

    def _sync_controls_from_state(self, item):
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(processor.FILM_MODES.index(self.params.mode))
        self.mode_combo.blockSignals(False)
        self._update_mode_ui(self.params.mode)
        self.exposure_s.set(self.params.exposure)
        self.density_s.set(self.params.density)
        self.shadow_density_s.set(self.params.shadow_density)
        self.highlight_density_s.set(self.params.highlight_density)
        self.contrast_s.set(self.params.contrast)
        self.gamma_s.set(self.params.gamma)
        self.saturation_s.set(self.params.saturation)
        self.denoise_s.set(self.params.denoise)
        self.sharpen_s.set(self.params.sharpen)
        self.shift_r_s.set(self.params.shift_r)
        self.shift_g_s.set(self.params.shift_g)
        self.shift_b_s.set(self.params.shift_b)
        auto_exposure, auto_contrast, auto_gamma = item.auto_baseline
        self.exposure_s.set_default(auto_exposure)
        self.contrast_s.set_default(auto_contrast)
        self.gamma_s.set_default(auto_gamma)
        self._update_base_swatch()
        label = next((lbl for lbl, ratio in crop.ASPECT_PRESETS if ratio == self.aspect_ratio),
                     crop.ASPECT_PRESETS[0][0])
        self.aspect_combo.setCurrentText(label)
        self.straighten_s.set(self.straighten_angle)

    def _on_export_format_change(self):
        ext = dict(self.EXPORT_FORMATS)[self.format_combo.currentText()]
        if ext == "dng":
            self.profile_combo.setEnabled(False)
            self.profile_hint_lbl.setText("Linear DNG is raw data - no color\nprofile is embedded.")
        else:
            self.profile_combo.setEnabled(True)
            self.profile_hint_lbl.setText("")

    def _on_marks_changed(self, marked):
        n = len(marked)
        if n == 0:
            text = "Ctrl+click photos in the filmstrip\nto select several for batch export."
        elif n == 1:
            text = "1 photo selected for batch export."
        else:
            text = f"{n} photos selected for batch export."
        self.marked_lbl.setText(text)

    def _convert_and_save_one(self, full_arr, is_linear, params, crop_rect,
                               rotation_90, straighten_angle, out_path, ext, profile_name):
        working_full = self._apply_rotation_to(full_arr, rotation_90, straighten_angle)
        x0, y0, x1, y1 = crop.crop_pixel_box(working_full.shape, crop_rect)
        cropped = working_full[y0:y1, x0:x1]
        if ext == "dng":
            full_positive_linear = processor.convert_linear(cropped, params, is_linear)
            processor.save_linear_dng(out_path, full_positive_linear)
        else:
            full_positive = processor.convert(cropped, params, is_linear)
            uint8_img = processor.to_uint8(full_positive)
            converted, icc_bytes = processor.convert_to_profile(uint8_img, profile_name)
            Image.fromarray(converted).save(out_path, icc_profile=icc_bytes)

    def save_image(self):
        if self.full_arr is None:
            QMessageBox.information(self, "Nothing to save", "Open a negative first.")
            return
        ext = dict(self.EXPORT_FORMATS)[self.format_combo.currentText()]
        profile_name = self.profile_combo.currentText()
        default_name = f"converted.{ext}"
        if self.image_path:
            base = os.path.splitext(os.path.basename(self.image_path))[0]
            default_name = f"{base}_positive.{ext}"
        filters = {
            "tif": "TIFF (*.tif)",
            "png": "PNG (*.png)",
            "jpg": "JPEG (*.jpg)",
            "dng": "Linear DNG (*.dng)",
        }[ext]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save converted positive", default_name, filters
        )
        if not path:
            return
        try:
            self._convert_and_save_one(self.full_arr, self.is_linear, self.params, self.crop_rect,
                                        self.rotation_90, self.straighten_angle, path, ext, profile_name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not save image", str(exc))
            return
        self.status_lbl.setText(f"Saved {os.path.basename(path)}")

    def export_selected(self):
        marked = sorted(self.filmstrip.get_marked())
        if not marked:
            QMessageBox.information(self, "Nothing selected",
                                    "Ctrl+click two or more photos in the filmstrip first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the exported photos")
        if not folder:
            return
        ext = dict(self.EXPORT_FORMATS)[self.format_combo.currentText()]
        profile_name = self.profile_combo.currentText()

        if 0 <= self.current_photo_index < len(self.photos):
            current = self.photos[self.current_photo_index]
            current.params = self.params
            current.crop_rect = self.crop_rect
            current.aspect_ratio = self.aspect_ratio
            current.rotation_90 = self.rotation_90
            current.straighten_angle = self.straighten_angle

        saved, failed = 0, []
        for index in marked:
            item = self.photos[index]
            if not self._ensure_photo_loaded(item):
                failed.append(os.path.basename(item.path))
                continue
            base = os.path.splitext(os.path.basename(item.path))[0]
            out_path = os.path.join(folder, f"{base}_positive.{ext}")
            try:
                self._convert_and_save_one(item.full_arr, item.is_linear, item.params, item.crop_rect,
                                            item.rotation_90, item.straighten_angle,
                                            out_path, ext, profile_name)
                saved += 1
            except Exception as exc:
                failed.append(f"{os.path.basename(item.path)} ({exc})")

        if failed:
            QMessageBox.critical(self, "Some exports failed",
                                  f"Saved {saved} of {len(marked)}.\n\nFailed:\n" + "\n".join(failed))
        else:
            self.status_lbl.setText(
                f"Exported {saved} photo{'s' if saved != 1 else ''} to {os.path.basename(folder)}")

    # ---------- processing / rendering ----------

    def on_slider(self):
        self.params.exposure = self.exposure_s.get()
        self.params.density = self.density_s.get()
        self.params.shadow_density = self.shadow_density_s.get()
        self.params.highlight_density = self.highlight_density_s.get()
        self.params.contrast = self.contrast_s.get()
        self.params.gamma = self.gamma_s.get()
        self.params.saturation = self.saturation_s.get()
        self.params.denoise = self.denoise_s.get()
        self.params.sharpen = self.sharpen_s.get()
        self.params.shift_r = self.shift_r_s.get()
        self.params.shift_g = self.shift_g_s.get()
        self.params.shift_b = self.shift_b_s.get()
        self.render_preview()

    def reset_adjustments(self):
        self.params.reset_adjustments()
        self.density_s.set(self.params.density)
        self.shadow_density_s.set(self.params.shadow_density)
        self.highlight_density_s.set(self.params.highlight_density)
        self.saturation_s.set(self.params.saturation)
        self.denoise_s.set(self.params.denoise)
        self.sharpen_s.set(self.params.sharpen)
        self.shift_r_s.set(self.params.shift_r)
        self.shift_g_s.set(self.params.shift_g)
        self.shift_b_s.set(self.params.shift_b)
        self._apply_auto_levels()

    def auto_base(self):
        if self.preview_arr is None:
            return
        if self.params.mode == "B&W":
            # Same reason the Film Base section is hidden for B&W in the
            # Colors tab: a grayscale scan has no per-channel color cast to
            # correct, and the auto-exposure step below would exactly
            # cancel out any base-color change anyway - so this would
            # silently do nothing without an explanation.
            self.status_lbl.setText(
                "Auto Base Color has no effect on B&W scans - there's no color cast to correct.")
            return
        self.params.base_color = processor.estimate_base_color(self.preview_arr)
        self._update_base_swatch()
        self._apply_auto_levels()

    def _on_mode_change(self, index):
        mode = processor.FILM_MODES[index]
        if mode == self.params.mode:
            return
        self.params.mode = mode
        if mode == "E-6":
            # Slides have no orange mask to neutralize - start from a
            # neutral reference rather than whatever was last sampled.
            self.params.base_color = (1.0, 1.0, 1.0)
        elif self.preview_arr is not None:
            self.params.base_color = processor.estimate_base_color(self.preview_arr)
        self._update_base_swatch()
        self._update_mode_ui(mode)
        self._apply_auto_levels()

    def _update_mode_ui(self, mode):
        # B&W collapses to neutral gray regardless of the Red/Green/Blue
        # sliders (see processor.convert_linear), so hide them rather than
        # leave controls that have no visible effect. The film-base sample
        # is equally moot: a B&W scan has R==G==B everywhere, so resampling
        # it is just a constant density shift that _apply_auto_levels()
        # (run right after every sample) exactly cancels back out via its
        # own exposure term - the pipette would visibly do nothing.
        show_color = mode != "B&W"
        self.color_balance_section.setVisible(show_color)
        self.film_base_section.setVisible(show_color)
        if not show_color:
            self._set_pipette_active(False)
        self.base_hint_lbl.setText(_film_base_hint(mode))

    def _apply_auto_levels(self):
        if self.preview_arr is None:
            self.render_preview()
            return
        exposure, contrast, gamma = processor.auto_levels(
            self.preview_arr, self.params.base_color, self.is_linear,
            positive=self.params.mode == "E-6")
        self.params.exposure = exposure
        self.params.contrast = contrast
        self.params.gamma = gamma
        self.exposure_s.set(exposure)
        self.contrast_s.set(contrast)
        self.gamma_s.set(gamma)
        self.exposure_s.set_default(exposure)
        self.contrast_s.set_default(contrast)
        self.gamma_s.set_default(gamma)
        if 0 <= self.current_photo_index < len(self.photos):
            self.photos[self.current_photo_index].auto_baseline = (exposure, contrast, gamma)
        self.render_preview()

    def _update_base_swatch(self):
        r, g, b = (int(np.clip(c, 0, 1) * 255) for c in self.params.base_color)
        self.base_swatch.set_color(f"#{r:02x}{g:02x}{b:02x}")
        self.base_lbl.setText(f"R{r} G{g} B{b}")

    def render_preview(self):
        if self.preview_arr is None:
            return
        zoom_scale = ZOOM_LEVELS[self._zoom_index]
        if zoom_scale is not None and not self.crop_mode and self.full_arr is not None:
            self._render_preview_zoomed(zoom_scale)
        else:
            self._render_preview_fit()

    def _render_preview_fit(self):
        self._working_arr = self._apply_rotation(self.preview_arr)
        working = self._working_arr
        ph, pw = working.shape[:2]
        if self.crop_mode:
            source = working
            origin_px = (0, 0)
        else:
            x0, y0, x1, y1 = crop.crop_pixel_box((ph, pw), self.crop_rect)
            source = working[y0:y1, x0:x1]
            origin_px = (x0, y0)

        positive = processor.convert(source, self.params, self.is_linear)
        positive_uint8 = processor.to_uint8(positive)
        img = Image.fromarray(positive_uint8)
        self.histogram.update_image(positive_uint8)

        cw = max(self.image_canvas.width(), 100)
        ch = max(self.image_canvas.height(), 100)
        iw, ih = img.size
        fit = min(cw / iw, ch / ih, 1.0) if (iw > cw or ih > ch) else min(cw / iw, ch / ih)
        fit *= IMAGE_FIT_SCALE
        disp_w, disp_h = max(1, int(iw * fit)), max(1, int(ih * fit))
        if (disp_w, disp_h) != (iw, ih):
            img = img.resize((disp_w, disp_h), Image.BILINEAR)

        self._sample_arr = working
        self._place_rendered_image(img, disp_w / iw, origin_px)

        if self.crop_mode:
            self._draw_crop_overlay()
        else:
            self.image_canvas.clear_overlay()

    def _render_preview_zoomed(self, scale):
        working_full = self._apply_rotation(self.full_arr)
        H, W = working_full.shape[:2]
        x0, y0, x1, y1 = crop.crop_pixel_box((H, W), self.crop_rect)
        cropped_full = working_full[y0:y1, x0:x1]
        full_h, full_w = cropped_full.shape[:2]

        cw = max(self.image_canvas.width(), 100)
        ch = max(self.image_canvas.height(), 100)
        # Window sized in *image* pixels so that, once resized by `scale`
        # for display, it fills the canvas - e.g. at 50% we need twice as
        # many source pixels as the canvas has display pixels.
        win_w = min(full_w, max(1, int(round(cw / scale))))
        win_h = min(full_h, max(1, int(round(ch / scale))))

        cx = int(self._zoom_center[0] * full_w)
        cy = int(self._zoom_center[1] * full_h)
        wx0 = int(np.clip(cx - win_w // 2, 0, max(0, full_w - win_w)))
        wy0 = int(np.clip(cy - win_h // 2, 0, max(0, full_h - win_h)))
        window = cropped_full[wy0:wy0 + win_h, wx0:wx0 + win_w]

        positive = processor.convert(window, self.params, self.is_linear)
        positive_uint8 = processor.to_uint8(positive)
        img = Image.fromarray(positive_uint8)
        self.histogram.update_image(positive_uint8)

        disp_w = max(1, int(round(win_w * scale)))
        disp_h = max(1, int(round(win_h * scale)))
        if (disp_w, disp_h) != (win_w, win_h):
            img = img.resize((disp_w, disp_h), Image.BILINEAR)

        self._sample_arr = window
        # Remember where this window sits within the full crop, so a
        # double-click while zoomed can be converted back to a crop-relative
        # fraction (on_canvas_double_click) regardless of which zoom level
        # is currently showing.
        self._zoom_window_origin = (wx0, wy0)
        self._zoom_full_dims = (full_w, full_h)
        self._place_rendered_image(img, scale, (0, 0))
        self.image_canvas.clear_overlay()

    def _place_rendered_image(self, img_pil, display_scale, origin_px):
        arr = np.ascontiguousarray(np.asarray(img_pil, dtype=np.uint8))
        pixmap = numpy_to_pixmap(arr)

        cw = max(self.image_canvas.width(), 100)
        ch = max(self.image_canvas.height(), 100)
        ox = (cw - pixmap.width()) // 2
        oy = (ch - pixmap.height()) // 2

        self._img_offset = (ox, oy)
        self._img_display_scale = display_scale
        self._display_origin_px = origin_px
        self.image_canvas.set_image(pixmap, ox, oy)

    # ---------- frame background menu ----------

    def _show_frame_menu(self, global_pos):
        menu = QMenu(self)
        for label, color in FRAME_COLORS:
            menu.addAction(label, lambda c=color: self._set_frame_color(c))
        menu.exec(global_pos)

    def _set_frame_color(self, color):
        self.frame_bg_color = color
        self.image_canvas.set_bg_color(color)
        self.render_preview()

    # ---------- crop tool ----------

    def on_tab_changed(self, index):
        self._tab_stack.setCurrentIndex(index)
        if index != TAB_COLORS:
            self._set_pipette_active(False)
        if self.full_arr is None:
            return
        is_crop_tab = index == TAB_CROP
        if is_crop_tab != self.crop_mode:
            self.crop_mode = is_crop_tab
            self.render_preview()

    def apply_crop(self):
        if self.full_arr is None:
            return
        self.crop_mode = False
        self.render_preview()

    def reset_crop(self):
        self.crop_rect = crop.FULL_RECT
        self.rotation_90 = 0
        self.straighten_angle = 0.0
        self.straighten_s.set(0.0)
        self.render_preview()

    def on_aspect_change(self):
        ratio = dict(crop.ASPECT_PRESETS)[self.aspect_combo.currentText()]
        self.aspect_ratio = ratio
        if self.full_arr is not None and ratio is not None:
            H, W = self._working_full_dims()
            self.crop_rect = crop.fit_rect_to_ratio(self.crop_rect, ratio, W, H)
        self.render_preview()

    def rotate_left(self):
        if self.full_arr is None:
            return
        self.rotation_90 = (self.rotation_90 - 1) % 4
        self.crop_rect = crop.FULL_RECT
        self.render_preview()

    def rotate_right(self):
        if self.full_arr is None:
            return
        self.rotation_90 = (self.rotation_90 + 1) % 4
        self.crop_rect = crop.FULL_RECT
        self.render_preview()

    def on_straighten_change(self):
        self.straighten_angle = self.straighten_s.get()
        if self.full_arr is not None and self.crop_rect == crop.FULL_RECT:
            h, w = self._working_full_dims()
            self.crop_rect = crop.safe_crop_for_straighten(self.straighten_angle, w, h)
        self.render_preview()

    def _on_straighten_drag_start(self):
        self._show_straighten_guides = True
        if self.crop_mode:
            self._draw_crop_overlay()

    def _on_straighten_drag_end(self):
        self._show_straighten_guides = False
        if self.crop_mode:
            self._draw_crop_overlay()

    def _apply_rotation(self, arr):
        return self._apply_rotation_to(arr, self.rotation_90, self.straighten_angle)

    @staticmethod
    def _apply_rotation_to(arr, rotation_90, straighten_angle):
        if rotation_90:
            arr = processor.rotate90(arr, rotation_90)
        if straighten_angle:
            arr = processor.rotate_arbitrary(arr, straighten_angle)
        return arr

    def _working_full_dims(self):
        h, w = self.full_arr.shape[:2]
        if self.rotation_90 % 2 == 1:
            h, w = w, h
        return h, w

    def _draw_crop_overlay(self):
        if self._working_arr is None:
            return
        ph, pw = self._working_arr.shape[:2]
        ox, oy = self._img_offset
        scale = self._img_display_scale
        fx0, fy0, fx1, fy1 = self.crop_rect

        ix0, iy0 = ox, oy
        ix1 = ox + pw * scale
        iy1 = oy + ph * scale
        cx0 = ox + fx0 * pw * scale
        cy0 = oy + fy0 * ph * scale
        cx1 = ox + fx1 * pw * scale
        cy1 = oy + fy1 * ph * scale

        self._crop_handles = {
            "tl": (cx0, cy0), "tr": (cx1, cy0),
            "bl": (cx0, cy1), "br": (cx1, cy1),
        }
        self._crop_rect_canvas = (cx0, cy0, cx1, cy1)

        self.image_canvas.set_overlay({
            "bg_color": self.frame_bg_color,
            "image_rect": (ix0, iy0, ix1, iy1),
            "crop_rect": (cx0, cy0, cx1, cy1),
            "handles": dict(self._crop_handles),
            "show_guides": self._show_straighten_guides,
        })

    def _hit_test_handle(self, x, y):
        for name, (hx, hy) in self._crop_handles.items():
            if (x - hx) ** 2 + (y - hy) ** 2 <= HANDLE_HIT_RADIUS ** 2:
                return name
        return None

    def _point_in_crop_rect(self, x, y):
        if not self._crop_rect_canvas:
            return False
        cx0, cy0, cx1, cy1 = self._crop_rect_canvas
        return cx0 <= x <= cx1 and cy0 <= y <= cy1

    # ---------- canvas interaction ----------

    def on_canvas_press(self, x, y):
        if self.full_arr is None:
            return
        if self.crop_mode:
            handle = self._hit_test_handle(x, y)
            if handle:
                self._crop_drag = {"mode": "resize", "corner": handle}
            elif self._point_in_crop_rect(x, y):
                self._crop_drag = {"mode": "move", "start": (x, y), "orig_rect": self.crop_rect}
            else:
                self._crop_drag = None
        elif self.pipette_active:
            self._sample_base_from_click(x, y)

    def on_canvas_double_click(self, x, y):
        if self.full_arr is None or self.crop_mode:
            return
        ox, oy = self._img_offset
        scale = self._img_display_scale
        ox_px, oy_px = self._display_origin_px
        img_x = ox_px + (x - ox) / scale
        img_y = oy_px + (y - oy) / scale

        if ZOOM_LEVELS[self._zoom_index] is None:
            # Currently fit-to-window: img_x/img_y are preview-resolution
            # coordinates within the crop rect - normalize directly.
            ph, pw = self._working_arr.shape[:2]
            x0, y0, x1, y1 = crop.crop_pixel_box((ph, pw), self.crop_rect)
            crop_w, crop_h = max(x1 - x0, 1), max(y1 - y0, 1)
            fx = float(np.clip((img_x - x0) / crop_w, 0.0, 1.0))
            fy = float(np.clip((img_y - y0) / crop_h, 0.0, 1.0))
        else:
            # Currently zoomed (50% or 100%): img_x/img_y are pixel coords
            # within the displayed window, not the full crop - add the
            # window's own offset (from the last _render_preview_zoomed
            # call) before normalizing, so the fraction stays crop-relative
            # no matter which zoom level we're coming from.
            wx0, wy0 = self._zoom_window_origin
            full_w, full_h = self._zoom_full_dims
            fx = float(np.clip((wx0 + img_x) / max(full_w, 1), 0.0, 1.0))
            fy = float(np.clip((wy0 + img_y) / max(full_h, 1), 0.0, 1.0))

        self._zoom_center = (fx, fy)
        self._zoom_index = (self._zoom_index + 1) % len(ZOOM_LEVELS)
        self.render_preview()

    def _on_pipette_toggle(self, active):
        self.pipette_active = active
        self.image_canvas.set_cursor_crosshair(active)

    def _set_pipette_active(self, active):
        if self.pipette_active == active:
            return
        self.pipette_active = active
        self.pipette_btn.set_active(active)
        self.image_canvas.set_cursor_crosshair(active)

    def on_canvas_drag(self, x, y):
        if not self.crop_mode or self._crop_drag is None or self._working_arr is None:
            return
        ph, pw = self._working_arr.shape[:2]
        ox, oy = self._img_offset
        scale = self._img_display_scale
        H, W = self._working_full_dims()

        fx = min(max((x - ox) / scale / pw, 0.0), 1.0)
        fy = min(max((y - oy) / scale / ph, 0.0), 1.0)

        if self._crop_drag["mode"] == "move":
            start_x, start_y = self._crop_drag["start"]
            dfx = (x - start_x) / scale / pw
            dfy = (y - start_y) / scale / ph
            fx0, fy0, fx1, fy1 = self._crop_drag["orig_rect"]
            w, h = fx1 - fx0, fy1 - fy0
            nx0, nx1 = crop.clamp_range(fx0 + dfx, fx0 + dfx + w)
            ny0, ny1 = crop.clamp_range(fy0 + dfy, fy0 + dfy + h)
            self.crop_rect = (nx0, ny0, nx1, ny1)
        else:
            corner = self._crop_drag["corner"]
            fx0, fy0, fx1, fy1 = self.crop_rect
            anchor_x = fx1 if corner in ("tl", "bl") else fx0
            anchor_y = fy1 if corner in ("tl", "tr") else fy0
            new_x, new_y = crop.resize_corner((anchor_x, anchor_y), (fx, fy),
                                               self.aspect_ratio, W, H)
            if corner in ("tl", "bl"):
                fx0 = new_x
            else:
                fx1 = new_x
            if corner in ("tl", "tr"):
                fy0 = new_y
            else:
                fy1 = new_y
            if fx1 - fx0 >= crop.MIN_SIZE and fy1 - fy0 >= crop.MIN_SIZE:
                self.crop_rect = (min(fx0, fx1), min(fy0, fy1), max(fx0, fx1), max(fy0, fy1))

        self._draw_crop_overlay()

    def on_canvas_release(self):
        self._crop_drag = None

    def _sample_base_from_click(self, x, y):
        if self._sample_arr is None:
            return
        ox, oy = self._img_offset
        scale = self._img_display_scale
        ox_px, oy_px = self._display_origin_px
        img_x = int(ox_px + (x - ox) / scale)
        img_y = int(oy_px + (y - oy) / scale)
        ph, pw = self._sample_arr.shape[:2]
        if not (0 <= img_x < pw and 0 <= img_y < ph):
            return
        self.params.base_color = processor.sample_base_color(self._sample_arr, img_x, img_y)
        self._update_base_swatch()
        self._apply_auto_levels()


def main():
    from PySide6.QtWidgets import QApplication, QStyleFactory
    from PySide6.QtGui import QFont
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NegConvert")
    app.setStyle(QStyleFactory.create("Fusion"))

    if sys.platform == "darwin":
        # San Francisco, via its private alias. macOS's own font smoothing
        # makes hinting look worse here, unlike Windows/Linux, hence the
        # opposite hinting preference from the Windows branch below.
        font = QFont(".AppleSystemUIFont", 13)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
    elif sys.platform == "win32":
        font = QFont("Segoe UI", 13)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        app.setFont(font)
    # else (Linux): desktop environments vary too much to guess a good
    # hardcoded choice - leave Qt/fontconfig's own default alone.

    window = NegConvertApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
