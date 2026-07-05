"""Custom canvas-drawn widgets for a modern look ttk can't easily give us:
pill-shaped buttons, a slider with a filled track and round handle, and an
RGB histogram."""
import tkinter as tk
import tkinter.font as tkfont

import numpy as np

from . import theme


def round_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class PillButton(tk.Canvas):
    """A rounded, flat button with hover/press feedback."""

    def __init__(self, parent, text, command=None, accent=False, bg=theme.PANEL,
                 padx=18, pady=10, font=("Helvetica", 11)):
        self._command = command
        self._accent = accent
        self._text = text
        self._font = tkfont.Font(family=font[0], size=font[1],
                                  weight=font[2] if len(font) > 2 else "normal")

        text_w = self._font.measure(text)
        text_h = self._font.metrics("linespace")
        self._btn_w = text_w + padx * 2
        self._btn_h = text_h + pady

        super().__init__(parent, width=self._btn_w, height=self._btn_h, bg=bg,
                          highlightthickness=0, cursor="hand2")

        self._state = "normal"
        self._draw()
        self.bind("<Enter>", lambda e: self._set_state("hover"))
        self.bind("<Leave>", lambda e: self._set_state("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._set_state("pressed"))
        self.bind("<ButtonRelease-1>", self._on_release)

    def _colors(self):
        if self._accent:
            fg = "#2b2b2b"
            return {
                "normal": theme.ACCENT_DARK,
                "hover": theme.ACCENT,
                "pressed": theme.ACCENT_DARK,
            }[self._state], fg
        fg = theme.TEXT
        return {
            "normal": theme.PANEL_DARK,
            "hover": theme.PANEL_HOVER,
            "pressed": theme.PANEL_DARK,
        }[self._state], fg

    def _set_state(self, state):
        self._state = state
        self._draw()

    def set_active(self, active):
        """Toggle the accent (pressed-looking) appearance, e.g. for a mode toggle."""
        self._accent = active
        self._state = "normal"
        self._draw()

    def _draw(self):
        self.delete("all")
        fill, fg = self._colors()
        round_rectangle(self, 1, 1, self._btn_w - 1, self._btn_h - 1, self._btn_h / 2,
                         fill=fill, outline="")
        self.create_text(self._btn_w / 2, self._btn_h / 2, text=self._text, fill=fg, font=self._font)

    def _on_release(self, event):
        inside = 0 <= event.x <= self._btn_w and 0 <= event.y <= self._btn_h
        self._set_state("hover" if inside else "normal")
        if inside and self._command:
            self._command()


class ModernSlider(tk.Frame):
    """A labeled slider with a filled rounded track and a round handle."""

    TRACK_H = 6
    HANDLE_R = 9

    def __init__(self, parent, label, frm, to, initial, on_change, value_fmt="{:.2f}", bg=theme.PANEL):
        super().__init__(parent, bg=bg)
        self._frm = frm
        self._to = to
        self._value = initial
        self._on_change = on_change
        self._fmt = value_fmt

        header = tk.Frame(self, bg=bg)
        header.pack(fill="x")
        tk.Label(header, text=label, bg=bg, fg=theme.TEXT,
                  font=("Helvetica", 11), anchor="w").pack(side="left")
        self._value_lbl = tk.Label(header, text=value_fmt.format(initial), bg=bg,
                                    fg=theme.ACCENT, font=("Helvetica", 11, "bold"), anchor="e")
        self._value_lbl.pack(side="right")

        self.canvas = tk.Canvas(self, height=28, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="x", pady=(6, 16))
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._on_pointer)
        self.canvas.bind("<B1-Motion>", self._on_pointer)

    def _bounds(self):
        w = max(self.canvas.winfo_width(), 1)
        pad = self.HANDLE_R + 2
        return pad, max(pad + 1, w - pad)

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        x0, x1 = self._bounds()
        y = 14
        span = self._to - self._frm
        frac = 0.0 if span == 0 else min(1.0, max(0.0, (self._value - self._frm) / span))
        hx = x0 + frac * (x1 - x0)

        c.create_line(x0, y, x1, y, fill=theme.TROUGH, width=self.TRACK_H, capstyle=tk.ROUND)
        if hx > x0:
            c.create_line(x0, y, hx, y, fill=theme.ACCENT, width=self.TRACK_H, capstyle=tk.ROUND)
        c.create_oval(hx - self.HANDLE_R, y - self.HANDLE_R, hx + self.HANDLE_R, y + self.HANDLE_R,
                       fill=theme.HANDLE, outline=theme.ACCENT_DARK, width=2)

    def _on_pointer(self, event):
        x0, x1 = self._bounds()
        frac = 0.0 if x1 <= x0 else min(1.0, max(0.0, (event.x - x0) / (x1 - x0)))
        self._value = self._frm + frac * (self._to - self._frm)
        self._value_lbl.configure(text=self._fmt.format(self._value))
        self._redraw()
        self._on_change()

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self._value_lbl.configure(text=self._fmt.format(value))
        self._redraw()


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


class Histogram(tk.Canvas):
    """An RGB histogram of a uint8 HxWx3 image, drawn as filled, overlapping
    translucent curves (like Lightroom/Photoshop) - true alpha-blended color
    mixing (R+G -> yellow, all three -> near white, etc.) needs a real
    compositing pass, which plain Canvas shapes/stipple can't do, so the
    fill is rendered as an RGB image via numpy/PIL and a crisp stroke is
    drawn on top of it with ordinary canvas lines.
    """

    BINS = 128
    CHANNEL_COLORS = ((255, 90, 90), (95, 220, 130), (100, 150, 255))  # R, G, B
    FILL_ALPHA = 0.5
    STROKE_COLORS = ("#ff9d9d", "#8bffb0", "#9dc4ff")

    def __init__(self, parent, height=120, bg=None):
        bg = bg or theme.CANVAS_BG
        super().__init__(parent, height=height, bg=bg, highlightthickness=0)
        self._bg_rgb = _hex_to_rgb(bg)
        self._image = None
        self._photo = None
        self.bind("<Configure>", lambda e: self._redraw())

    def update_image(self, image_uint8):
        self._image = image_uint8
        self._redraw()

    def clear(self):
        self._image = None
        self.delete("all")

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1 or self._image is None:
            return

        # Lazy import: keeps this module importable even if PIL is ever
        # unavailable at widget-construction time (only needed for drawing).
        from PIL import Image, ImageTk

        pad_x, pad_y = 4, 6
        plot_w = max(1, w - 2 * pad_x)
        plot_h = max(1, h - 2 * pad_y)

        canvas_arr = np.tile(np.array(self._bg_rgb, dtype=np.float32), (h, w, 1))
        bin_x = np.arange(self.BINS)
        col_x = np.linspace(0, self.BINS - 1, plot_w)
        row_y = np.arange(h, dtype=np.float32)[:, None]  # (h, 1)

        curves = []
        for ch, fill_color in enumerate(self.CHANNEL_COLORS):
            channel = self._image[..., ch].ravel()
            counts, _ = np.histogram(channel, bins=self.BINS, range=(0, 255))
            counts = np.log1p(counts.astype(np.float64))
            peak = counts.max()
            norm = counts / peak if peak > 0 else counts
            curve = np.interp(col_x, bin_x, norm)
            curves.append(curve)

            fill_top_y = pad_y + (1.0 - curve) * plot_h  # (plot_w,), top of fill per column
            filled = row_y >= fill_top_y[None, :]  # (h, plot_w) bool
            alpha = filled.astype(np.float32) * self.FILL_ALPHA

            region = canvas_arr[:, pad_x:pad_x + plot_w, :]
            fg = np.array(fill_color, dtype=np.float32)[None, None, :]
            canvas_arr[:, pad_x:pad_x + plot_w, :] = fg * alpha[..., None] + region * (1.0 - alpha[..., None])

        photo_img = Image.fromarray(np.clip(canvas_arr, 0, 255).astype(np.uint8), mode="RGB")
        self._photo = ImageTk.PhotoImage(photo_img)
        self.create_image(0, 0, anchor="nw", image=self._photo, tags=("hist_fill",))

        for curve, stroke in zip(curves, self.STROKE_COLORS):
            points = []
            for i, v in enumerate(curve):
                x = pad_x + i
                y = pad_y + (1.0 - v) * plot_h
                points.extend((x, y))
            if len(points) >= 4:
                self.create_line(*points, fill=stroke, width=1.3, smooth=True, tags=("hist_stroke",))


class TabBar(tk.Frame):
    """A row of rounded pill tabs, exactly one selected at a time - a
    modern, fully-rounded stand-in for ttk.Notebook's square tab strip."""

    def __init__(self, parent, labels, on_change, bg=None):
        bg = bg or theme.PANEL
        super().__init__(parent, bg=bg)
        self._on_change = on_change
        self._buttons = []
        for i, label in enumerate(labels):
            btn = PillButton(self, label, command=lambda i=i: self.select(i), bg=bg,
                              padx=16, pady=8, font=("Helvetica", 11))
            btn.pack(side="left", padx=(0, 8) if i < len(labels) - 1 else 0)
            self._buttons.append(btn)
        self._selected = 0
        self._buttons[0].set_active(True)

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
