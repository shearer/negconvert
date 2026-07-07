"""Custom canvas-drawn widgets for a modern look ttk can't easily give us:
pill-shaped buttons, a slider with a filled track and round handle, an RGB
histogram, and a scrollable thumbnail filmstrip."""
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

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

    TRACK_H = 4
    HANDLE_R = 7

    def __init__(self, parent, label, frm, to, initial, on_change, value_fmt="{:.2f}", bg=theme.PANEL,
                 default=None):
        super().__init__(parent, bg=bg)
        self._frm = frm
        self._to = to
        self._value = initial
        self._default = initial if default is None else default
        self._on_change = on_change
        self._fmt = value_fmt

        header = tk.Frame(self, bg=bg)
        header.pack(fill="x")
        tk.Label(header, text=label, bg=bg, fg=theme.TEXT,
                  font=("Helvetica", 11), anchor="w").pack(side="left")
        self._value_lbl = tk.Label(header, text=value_fmt.format(initial), bg=bg,
                                    fg=theme.ACCENT, font=("Helvetica", 11), anchor="e")
        self._value_lbl.pack(side="right")

        self.canvas = tk.Canvas(self, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="x", pady=(2, 5))
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._on_pointer)
        self.canvas.bind("<B1-Motion>", self._on_pointer)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

    def _bounds(self):
        w = max(self.canvas.winfo_width(), 1)
        pad = self.HANDLE_R + 2
        return pad, max(pad + 1, w - pad)

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        x0, x1 = self._bounds()
        y = max(c.winfo_height(), 1) / 2
        span = self._to - self._frm
        frac = 0.0 if span == 0 else min(1.0, max(0.0, (self._value - self._frm) / span))
        hx = x0 + frac * (x1 - x0)

        c.create_line(x0, y, x1, y, fill=theme.TROUGH, width=self.TRACK_H, capstyle=tk.ROUND)
        if hx > x0:
            c.create_line(x0, y, hx, y, fill=theme.ACCENT, width=self.TRACK_H, capstyle=tk.ROUND)
        c.create_oval(hx - self.HANDLE_R, y - self.HANDLE_R, hx + self.HANDLE_R, y + self.HANDLE_R,
                       fill=theme.HANDLE, outline=theme.ACCENT_DARK, width=1)

    def _on_pointer(self, event):
        x0, x1 = self._bounds()
        frac = 0.0 if x1 <= x0 else min(1.0, max(0.0, (event.x - x0) / (x1 - x0)))
        self._value = self._frm + frac * (self._to - self._frm)
        self._value_lbl.configure(text=self._fmt.format(self._value))
        self._redraw()
        self._on_change()

    def _on_double_click(self, _event):
        self._value = self._default
        self._value_lbl.configure(text=self._fmt.format(self._value))
        self._redraw()
        self._on_change()

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self._value_lbl.configure(text=self._fmt.format(value))
        self._redraw()

    def set_default(self, value):
        """Update what a double-click resets to, without touching the
        current displayed value (e.g. re-baselining after auto-levels)."""
        self._default = value


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


class Histogram(tk.Canvas):
    """An RGB histogram of a uint8 HxWx3 image - filled, overlapping curves
    on a near-black background, in the style of darktable/Lightroom.

    Overlapping channels are combined with a *screen* blend (result = 1 -
    (1-a)*(1-b)) rather than plain alpha-over: screen blending brightens
    where colors overlap (red+green -> vivid yellow, all three -> near
    white), matching how real darkroom histogram tools render channel
    overlap. Plain alpha-over instead muddies overlaps toward brown, which
    is what a plain Canvas fill/stipple would give. That compositing needs
    a real per-pixel blend, so the fill is rendered as an RGB image via
    numpy/PIL, with a crisp stroke drawn on top using ordinary canvas lines.
    """

    BINS = 128
    CHANNEL_COLORS = ((255, 60, 60), (60, 230, 100), (70, 130, 255))  # R, G, B
    FILL_INTENSITY = 0.85   # channel color strength fed into the screen blend
    STROKE_COLORS = ((255, 140, 140), (140, 255, 170), (150, 190, 255))
    AA_WIDTH = 1.25         # soft-edge width, in pixels, at the top of each fill

    def __init__(self, parent, height=120, bg=None):
        bg = bg or theme.HIST_BG
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

        canvas_norm = np.tile(np.array(self._bg_rgb, dtype=np.float32) / 255.0, (h, w, 1))
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
            # soft anti-aliased edge: 0 above the curve, 1 a bit below it
            coverage = np.clip((row_y - fill_top_y[None, :]) / self.AA_WIDTH + 0.5, 0.0, 1.0)

            fg = np.array(fill_color, dtype=np.float32) / 255.0 * self.FILL_INTENSITY
            blend = coverage[..., None] * fg[None, None, :]
            region = canvas_norm[:, pad_x:pad_x + plot_w, :]
            canvas_norm[:, pad_x:pad_x + plot_w, :] = 1.0 - (1.0 - region) * (1.0 - blend)

        photo_img = Image.fromarray(np.clip(canvas_norm * 255.0, 0, 255).astype(np.uint8), mode="RGB")
        self._photo = ImageTk.PhotoImage(photo_img)
        self.create_image(0, 0, anchor="nw", image=self._photo, tags=("hist_fill",))

        for curve, stroke in zip(curves, self.STROKE_COLORS):
            points = []
            for i, v in enumerate(curve):
                x = pad_x + i
                y = pad_y + (1.0 - v) * plot_h
                points.extend((x, y))
            if len(points) >= 4:
                self.create_line(*points, fill="#%02x%02x%02x" % stroke, width=1.3,
                                  smooth=True, tags=("hist_stroke",))


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


class Filmstrip(tk.Frame):
    """A horizontally scrollable strip of thumbnails, one per open photo,
    for batch editing. Click a cell (or the photo isn't loaded yet - a
    plain filename label stands in until a thumbnail is available) to
    switch to that photo. Ctrl+click toggles a cell in/out of a separate
    multi-selection (for batch export), shown with a different-colored
    border than the single "currently active" photo."""

    THUMB_W = 84
    THUMB_H = 64
    MARK_COLOR = "#5c9fff"

    def __init__(self, parent, on_select, on_mark_change=None, bg=None):
        bg = bg or theme.PANEL_DARK
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._on_select = on_select
        self._on_mark_change = on_mark_change
        self._cells = []
        self._selected = -1
        self._marked = set()

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, height=self.THUMB_H + 24)
        hbar = ttk.Scrollbar(self, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=hbar.set)
        self._canvas.pack(side="top", fill="x")
        hbar.pack(side="top", fill="x")

        self._inner = tk.Frame(self._canvas, bg=bg)
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                          lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self._canvas.xview_scroll(int(-event.delta), "units")

    def set_photos(self, paths_and_thumbs):
        """paths_and_thumbs: list of (path, PIL.Image or None)."""
        from PIL import Image, ImageTk

        for cell in self._cells:
            cell["frame"].destroy()
        self._cells = []
        self._selected = -1
        self._marked = set()

        for i, (path, pil_img) in enumerate(paths_and_thumbs):
            frame = tk.Frame(self._inner, bg=self._bg, width=self.THUMB_W + 8, height=self.THUMB_H + 8,
                              highlightthickness=2, highlightbackground=self._bg)
            frame.pack_propagate(False)
            frame.pack(side="left", padx=3, pady=3)

            label = tk.Label(frame, bg=self._bg)
            label.pack(expand=True, fill="both")

            photo_ref = None
            if pil_img is not None:
                thumb = pil_img.copy()
                thumb.thumbnail((self.THUMB_W, self.THUMB_H), Image.BILINEAR)
                photo_ref = ImageTk.PhotoImage(thumb)
                label.configure(image=photo_ref, text="")
            else:
                label.configure(text=os.path.basename(path), fg=theme.TEXT_DIM,
                                 font=("Helvetica", 8), wraplength=self.THUMB_W, justify="center")

            for widget in (frame, label):
                widget.bind("<Button-1>", lambda e, idx=i: self._on_click(idx, e))

            self._cells.append({"frame": frame, "label": label, "photo_ref": photo_ref})

    def update_thumbnail(self, index, pil_img):
        """Swap in a real thumbnail for a cell that was a placeholder."""
        from PIL import Image, ImageTk

        if not (0 <= index < len(self._cells)) or pil_img is None:
            return
        thumb = pil_img.copy()
        thumb.thumbnail((self.THUMB_W, self.THUMB_H), Image.BILINEAR)
        photo_ref = ImageTk.PhotoImage(thumb)
        cell = self._cells[index]
        cell["photo_ref"] = photo_ref
        cell["label"].configure(image=photo_ref, text="")

    def _on_click(self, index, event):
        # Control mask is bit 0x0004 on every platform Tk runs on.
        if event.state & 0x0004:
            self.toggle_mark(index)
        else:
            self._on_select(index)

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
            self._on_mark_change(set(self._marked))

    def _redraw_highlight(self, index):
        if not (0 <= index < len(self._cells)):
            return
        if index == self._selected:
            color = theme.ACCENT
        elif index in self._marked:
            color = self.MARK_COLOR
        else:
            color = self._bg
        self._cells[index]["frame"].configure(highlightbackground=color)

    def set_selected(self, index):
        previous = self._selected
        self._selected = index
        if 0 <= previous < len(self._cells):
            self._redraw_highlight(previous)
        if 0 <= index < len(self._cells):
            self._redraw_highlight(index)
