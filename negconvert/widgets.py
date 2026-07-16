"""Custom PySide6 widgets: pill buttons, modern slider, histogram, filmstrip."""
import os
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QImage,
    QPainterPath, QFont, QFontMetrics,
)

from . import theme


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def numpy_to_pixmap(arr_uint8):
    """Convert a uint8 HxWx3 numpy array to a QPixmap."""
    arr = np.ascontiguousarray(arr_uint8)
    h, w = arr.shape[:2]
    qimg = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class PillButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None, text="", command=None, accent=False,
                 bg=None, padx=18, pady=10, font=None):
        super().__init__(parent)
        self._text = text
        self._command = command
        self._accent = accent
        self._bg = bg or theme.PANEL
        self._state = "normal"

        font_family, font_size, bold = "Helvetica", 12, False
        if font:
            font_family = font[0]
            font_size = font[1]
            bold = len(font) > 2 and font[2] == "bold"

        self._font = QFont(font_family, font_size)
        self._font.setBold(bold)

        fm = QFontMetrics(self._font)
        self._btn_w = fm.horizontalAdvance(text) + padx * 2
        self._btn_h = fm.height() + pady
        self.setFixedSize(self._btn_w, self._btn_h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _fill_color(self):
        if self._accent:
            return {"normal": theme.ACCENT_DARK, "hover": theme.ACCENT, "pressed": theme.ACCENT_DARK}[self._state]
        return {"normal": theme.PANEL_DARK, "hover": theme.PANEL_HOVER, "pressed": theme.PANEL_DARK}[self._state]

    def _text_color(self):
        return "#2b2b2b" if self._accent else theme.TEXT

    def set_active(self, active):
        self._accent = active
        self._state = "normal"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(self._fill_color())))
        painter.setPen(Qt.PenStyle.NoPen)
        radius = self._btn_h / 2
        path = QPainterPath()
        path.addRoundedRect(1, 1, self._btn_w - 2, self._btn_h - 2, radius, radius)
        painter.drawPath(path)
        painter.setFont(self._font)
        painter.setPen(QColor(self._text_color()))
        painter.drawText(QRect(0, 0, self._btn_w, self._btn_h), Qt.AlignmentFlag.AlignCenter, self._text)

    def enterEvent(self, event):
        self._state = "hover"
        self.update()

    def leaveEvent(self, event):
        self._state = "normal"
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._state = "pressed"
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            inside = self.rect().contains(event.position().toPoint())
            self._state = "hover" if inside else "normal"
            self.update()
            if inside:
                self.clicked.emit()
                if self._command:
                    self._command()


class PipetteButton(QWidget):
    toggled = Signal(bool)
    SIZE = 30

    def __init__(self, parent=None, command=None, bg=None):
        super().__init__(parent)
        self._command = command
        self._active = False
        self._hover = False
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def is_active(self):
        return self._active

    def set_active(self, active):
        self._active = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._active:
            fill = QColor(theme.ACCENT)
        elif self._hover:
            fill = QColor(theme.PANEL_HOVER)
        else:
            fill = QColor(theme.PANEL_DARK)

        painter.setBrush(QBrush(fill))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(1, 1, self.SIZE - 2, self.SIZE - 2, 8, 8)
        painter.drawPath(path)

        icon_color = QColor("#2b2b2b" if self._active else theme.TEXT)
        painter.setBrush(QBrush(icon_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRect(16, 5, 8, 8))  # bulb

        pen = QPen(icon_color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(18, 11, 8, 21)  # tube

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(icon_color))
        painter.drawEllipse(QRect(6, 21, 4, 4))  # tip

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._active = not self._active
            self.update()
            self.toggled.emit(self._active)
            if self._command:
                self._command(self._active)


class _SliderTrack(QWidget):
    """The draggable track portion of ModernSlider."""
    TRACK_H = 3
    HANDLE_R = 8

    track_pressed = Signal()
    track_released = Signal()

    def __init__(self, parent, frm, to, initial, on_change, bg_color):
        super().__init__(parent)
        self._frm = frm
        self._to = to
        self._value = initial
        self._default = initial
        self._on_change = on_change
        self._bg_color = bg_color
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setMouseTracking(True)

    def _bounds(self):
        pad = self.HANDLE_R + 3
        return pad, max(pad + 1, self.width() - pad)

    def _frac(self):
        span = self._to - self._frm
        return 0.0 if span == 0 else min(1.0, max(0.0, (self._value - self._frm) / span))

    def set_value(self, value):
        self._value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, x1 = self._bounds()
        y = self.height() / 2
        frac = self._frac()
        hx = x0 + frac * (x1 - x0)

        # Trough (inactive portion)
        pen = QPen(QColor(theme.TROUGH), self.TRACK_H, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(x0), int(y), int(x1), int(y))

        # Filled portion
        if hx > x0:
            pen = QPen(QColor(theme.TROUGH_FILLED), self.TRACK_H, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(x0), int(y), int(hx), int(y))

        # Handle: white circle with a subtle ring on hover
        r = self.HANDLE_R
        if self._hover:
            painter.setPen(QPen(QColor(theme.ACCENT), 1.5))
            painter.setBrush(QBrush(QColor(theme.HANDLE)))
        else:
            painter.setPen(QPen(QColor(theme.HANDLE_BORDER), 1))
            painter.setBrush(QBrush(QColor(theme.HANDLE)))
        painter.drawEllipse(int(hx - r), int(y - r), r * 2, r * 2)

    def _update_from_x(self, x):
        x0, x1 = self._bounds()
        frac = 0.0 if x1 <= x0 else min(1.0, max(0.0, (x - x0) / (x1 - x0)))
        self._value = self._frm + frac * (self._to - self._frm)
        self.update()
        self._on_change()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def _update_from_x(self, x):
        x0, x1 = self._bounds()
        frac = 0.0 if x1 <= x0 else min(1.0, max(0.0, (x - x0) / (x1 - x0)))
        self._value = self._frm + frac * (self._to - self._frm)
        self.update()
        self._on_change()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._update_from_x(event.position().x())
            self.track_pressed.emit()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_x(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.track_released.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._value = self._default
            self.update()
            self._on_change()


class ModernSlider(QWidget):
    """Labeled slider with filled rounded track and round handle."""
    valueChanged = Signal()

    def __init__(self, parent=None, label="", frm=0.0, to=1.0, initial=0.0,
                 on_change=None, value_fmt="{:.2f}", bg=None, default=None):
        super().__init__(parent)
        self._frm = frm
        self._to = to
        self._value = initial
        self._on_change = on_change
        self._fmt = value_fmt
        self._bg_color = bg or theme.PANEL
        self.setStyleSheet(f"background: {self._bg_color};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 2)
        layout.setSpacing(1)

        header = QWidget(self)
        header.setStyleSheet(f"background: {self._bg_color};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label, header)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_LABEL}; background: {self._bg_color}; font-size: 11px;"
        )
        hl.addWidget(lbl)
        hl.addStretch()

        self._value_lbl = QLabel(value_fmt.format(initial), header)
        self._value_lbl.setStyleSheet(
            f"color: {theme.TEXT}; background: {self._bg_color}; font-size: 11px; font-weight: 500;"
        )
        hl.addWidget(self._value_lbl)
        layout.addWidget(header)

        self._track = _SliderTrack(self, frm, to, initial, self._track_changed, self._bg_color)
        if default is not None:
            self._track._default = default
        layout.addWidget(self._track)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _track_changed(self):
        self._value = self._track._value
        self._value_lbl.setText(self._fmt.format(self._value))
        if self._on_change:
            self._on_change()
        self.valueChanged.emit()

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self._track.set_value(value)
        self._value_lbl.setText(self._fmt.format(value))

    def set_default(self, value):
        self._track._default = value

    @property
    def track_pressed(self):
        return self._track.track_pressed

    @property
    def track_released(self):
        return self._track.track_released


class ColorSwatch(QWidget):
    """Small rounded rectangle showing a solid color."""

    def __init__(self, size=32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor("#808080")

    def set_color(self, color_str):
        self._color = QColor(color_str)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)
        painter.drawPath(path)


class Histogram(QWidget):
    """RGB histogram with screen-blended filled curves."""
    BINS = 128
    CHANNEL_COLORS = ((255, 60, 60), (60, 230, 100), (70, 130, 255))
    FILL_INTENSITY = 0.85
    STROKE_COLORS = ((255, 140, 140), (140, 255, 170), (150, 190, 255))
    AA_WIDTH = 1.25

    def __init__(self, parent=None, height=120, bg=None):
        super().__init__(parent)
        self._bg_color = bg or theme.HIST_BG
        self._bg_rgb = _hex_to_rgb(self._bg_color)
        self._image = None
        self._pixmap = None
        self._curves = []
        self._pad_x = 4
        self._pad_y = 6
        self._plot_h = max(1, height - 12)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def update_image(self, image_uint8):
        self._image = image_uint8
        self._rebuild_pixmap()
        self.update()

    def clear(self):
        self._image = None
        self._pixmap = None
        self._curves = []
        self.update()

    def _rebuild_pixmap(self):
        if self._image is None:
            self._pixmap = None
            return
        w, h = self.width(), self.height()
        if w <= 1 or h <= 1:
            return

        pad_x, pad_y = self._pad_x, self._pad_y
        plot_w = max(1, w - 2 * pad_x)
        plot_h = max(1, h - 2 * pad_y)
        self._plot_h = plot_h

        canvas_norm = np.tile(np.array(self._bg_rgb, dtype=np.float32) / 255.0, (h, w, 1))
        bin_x = np.arange(self.BINS)
        col_x = np.linspace(0, self.BINS - 1, plot_w)
        row_y = np.arange(h, dtype=np.float32)[:, None]

        self._curves = []
        for ch, fill_color in enumerate(self.CHANNEL_COLORS):
            channel = self._image[..., ch].ravel()
            counts, _ = np.histogram(channel, bins=self.BINS, range=(0, 255))
            counts = np.log1p(counts.astype(np.float64))
            peak = counts.max()
            norm = counts / peak if peak > 0 else counts
            curve = np.interp(col_x, bin_x, norm)
            self._curves.append(curve)

            fill_top_y = pad_y + (1.0 - curve) * plot_h
            coverage = np.clip((row_y - fill_top_y[None, :]) / self.AA_WIDTH + 0.5, 0.0, 1.0)
            fg = np.array(fill_color, dtype=np.float32) / 255.0 * self.FILL_INTENSITY
            blend = coverage[..., None] * fg[None, None, :]
            region = canvas_norm[:, pad_x:pad_x + plot_w, :]
            canvas_norm[:, pad_x:pad_x + plot_w, :] = 1.0 - (1.0 - region) * (1.0 - blend)

        arr = np.clip(canvas_norm * 255.0, 0, 255).astype(np.uint8)
        self._pixmap = numpy_to_pixmap(arr)

    def resizeEvent(self, event):
        self._rebuild_pixmap()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._bg_color))
        if self._pixmap:
            painter.drawPixmap(0, 0, self._pixmap)
        for curve, stroke in zip(self._curves, self.STROKE_COLORS):
            pen = QPen(QColor(*stroke), 1.3)
            painter.setPen(pen)
            path = QPainterPath()
            started = False
            for i, v in enumerate(curve):
                x = self._pad_x + i
                y = self._pad_y + (1.0 - v) * self._plot_h
                if not started:
                    path.moveTo(x, y)
                    started = True
                else:
                    path.lineTo(x, y)
            if started:
                painter.drawPath(path)


class TabBar(QWidget):
    def __init__(self, parent=None, labels=None, on_change=None, bg=None, active=0):
        super().__init__(parent)
        self._bg = bg or theme.PANEL
        self._on_change = on_change
        self._buttons = []
        self._selected = active

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for i, label in enumerate(labels or []):
            btn = PillButton(self, label, bg=self._bg, padx=16, pady=8)
            btn.clicked.connect(lambda i=i: self.select(i))
            layout.addWidget(btn)
            self._buttons.append(btn)
        layout.addStretch()

        if self._buttons:
            self._buttons[self._selected].set_active(True)

    def select(self, index):
        if index == self._selected:
            return
        self._buttons[self._selected].set_active(False)
        self._selected = index
        self._buttons[index].set_active(True)
        if self._on_change:
            self._on_change(index)

    def index(self):
        return self._selected


class _FilmstripCell(QFrame):
    clicked = Signal(int, bool)  # index, ctrl_held
    right_clicked = Signal(int, QPoint)  # index, global position
    THUMB_W = 84
    THUMB_H = 64

    def __init__(self, parent, index, path, pil_img):
        super().__init__(parent)
        self._index = index
        self.setFixedSize(self.THUMB_W + 8, self.THUMB_H + 24)
        self._apply_style(None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._img_label = QLabel(self)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setFixedSize(self.THUMB_W, self.THUMB_H)
        self._img_label.setStyleSheet(f"background: {theme.PANEL_DARK}; border: none;")
        layout.addWidget(self._img_label)

        if pil_img is not None:
            self._set_pixmap(pil_img)
        else:
            name = os.path.basename(path)
            self._img_label.setText(name)
            self._img_label.setWordWrap(True)
            self._img_label.setStyleSheet(
                f"color: {theme.TEXT_DIM}; background: {theme.PANEL_DARK}; font-size: 8px; border: none;"
            )

    def _set_pixmap(self, pil_img):
        from PIL import Image
        thumb = pil_img.copy()
        thumb.thumbnail((self.THUMB_W, self.THUMB_H), Image.BILINEAR)
        arr = np.ascontiguousarray(np.array(thumb.convert("RGB")))
        self._img_label.setPixmap(numpy_to_pixmap(arr))
        self._img_label.setStyleSheet(f"background: {theme.PANEL_DARK}; border: none;")

    def update_thumbnail(self, pil_img):
        self._set_pixmap(pil_img)

    def _apply_style(self, highlight_color):
        border = highlight_color or theme.PANEL_DARK
        self.setStyleSheet(
            f"QFrame {{ border: 2px solid {border}; background: {theme.PANEL_DARK}; border-radius: 3px; }}"
        )

    def set_highlight(self, color):
        self._apply_style(color)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.clicked.emit(self._index, ctrl)

    def contextMenuEvent(self, event):
        self.right_clicked.emit(self._index, event.globalPos())


class Filmstrip(QWidget):
    MARK_COLOR = "#5c9fff"

    def __init__(self, parent=None, on_select=None, on_mark_change=None, on_context_menu=None, bg=None):
        super().__init__(parent)
        self._bg = bg or theme.PANEL_DARK
        self._on_select = on_select
        self._on_mark_change = on_mark_change
        self._on_context_menu = on_context_menu
        self._cells = []
        self._selected = -1
        self._marked = set()
        self.setStyleSheet(f"background: {self._bg};")
        self.setFixedHeight(_FilmstripCell.THUMB_H + 44)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea(self)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"background: {self._bg}; border: none;")

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background: {self._bg};")
        self._inner_layout = QHBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        self._inner_layout.setSpacing(6)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    def set_photos(self, paths_and_thumbs):
        for cell in self._cells:
            cell.setParent(None)
            cell.deleteLater()
        self._cells = []
        self._selected = -1
        self._marked = set()

        while self._inner_layout.count():
            self._inner_layout.takeAt(0)

        for i, (path, pil_img) in enumerate(paths_and_thumbs):
            cell = _FilmstripCell(self._inner, i, path, pil_img)
            cell.clicked.connect(self._on_cell_click)
            cell.right_clicked.connect(self._on_cell_right_click)
            self._inner_layout.addWidget(cell)
            self._cells.append(cell)
        self._inner_layout.addStretch()

    def _on_cell_click(self, index, ctrl):
        if ctrl:
            self.toggle_mark(index)
        else:
            if self._marked:
                self.clear_marks()
            if self._on_select:
                self._on_select(index)

    def _on_cell_right_click(self, index, global_pos):
        if self._on_context_menu:
            self._on_context_menu(index, global_pos)

    def update_thumbnail(self, index, pil_img):
        if 0 <= index < len(self._cells):
            self._cells[index].update_thumbnail(pil_img)

    def toggle_mark(self, index):
        if index in self._marked:
            self._marked.discard(index)
        else:
            self._marked.add(index)
        self._redraw_highlight(index)
        if self._on_mark_change:
            self._on_mark_change(set(self._marked))

    def get_marked(self):
        return set(self._marked)

    def clear_marks(self):
        old = list(self._marked)
        self._marked = set()
        for i in old:
            self._redraw_highlight(i)
        if self._on_mark_change:
            self._on_mark_change(set())

    def _redraw_highlight(self, index):
        if not (0 <= index < len(self._cells)):
            return
        if index == self._selected:
            color = theme.ACCENT
        elif index in self._marked:
            color = self.MARK_COLOR
        else:
            color = None
        self._cells[index].set_highlight(color)

    def set_selected(self, index):
        previous = self._selected
        self._selected = index
        if 0 <= previous < len(self._cells):
            self._redraw_highlight(previous)
        if 0 <= index < len(self._cells):
            self._redraw_highlight(index)

    def wheelEvent(self, event):
        sb = self._scroll.horizontalScrollBar()
        sb.setValue(sb.value() - event.angleDelta().y())
