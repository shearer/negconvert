"""Tkinter UI for NegConvert."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageTk

from . import crop
from . import processor
from . import theme
from . import widgets
from .widgets import ModernSlider, PillButton

PREVIEW_MAX_DIM = 900
HANDLE_HIT_RADIUS = 12
CROP_HANDLE_R = 8


class NegConvertApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NegConvert — C-41 Negative Converter")
        self.root.geometry("1200x800")
        theme.apply(root)

        self.params = processor.Params()
        self.full_arr = None       # full resolution negative, float32 0..1
        self.preview_arr = None    # downscaled negative for interactive preview
        self.preview_scale = 1.0   # preview_dim / full_dim
        self.is_linear = False     # True for raw/DNG sources (no sRGB gamma)
        self.tk_image = None
        self.image_path = None

        self.crop_mode = False
        self.crop_rect = crop.FULL_RECT     # (fx0, fy0, fx1, fy1), fractional of full image
        self.aspect_ratio = None            # None = Free
        self._crop_drag = None
        self._crop_handles = {}
        self._crop_rect_canvas = None

        self._build_layout()
        self._bind_shortcuts()

    # ---------- layout ----------

    def _build_layout(self):
        toolbar = ttk.Frame(self.root, style="Panel.TFrame", padding=12)
        toolbar.pack(side="top", fill="x")

        PillButton(toolbar, "Open Negative…", command=self.open_image,
                   bg=theme.PANEL).pack(side="left", padx=4)
        self.crop_btn = PillButton(toolbar, "Crop", command=self.toggle_crop,
                                    bg=theme.PANEL)
        self.crop_btn.pack(side="left", padx=4)
        PillButton(toolbar, "Auto Base Color", command=self.auto_base,
                   bg=theme.PANEL).pack(side="left", padx=4)
        PillButton(toolbar, "Reset Adjustments", command=self.reset_adjustments,
                   bg=theme.PANEL).pack(side="left", padx=4)
        PillButton(toolbar, "Save As…", command=self.save_image, accent=True,
                   bg=theme.PANEL, font=("Helvetica", 11, "bold")).pack(side="right", padx=4)

        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)

        # canvas / preview area
        canvas_frame = ttk.Frame(body)
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=theme.CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas_placeholder = self.canvas.create_text(
            0, 0, text="Open a negative scan to begin\n(click the image later to sample the film base color)",
            fill=theme.TEXT_DIM, font=("Helvetica", 13), justify="center")
        self.canvas.bind("<Configure>", self._center_placeholder)

        # sidebar
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=18, width=300)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Adjustments", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))

        self.exposure_s = ModernSlider(sidebar, "Exposure (EV)", -2.0, 2.0, self.params.exposure, self.on_slider)
        self.exposure_s.pack(fill="x")
        self.contrast_s = ModernSlider(sidebar, "Contrast", 0.5, 2.5, self.params.contrast, self.on_slider)
        self.contrast_s.pack(fill="x")
        self.gamma_s = ModernSlider(sidebar, "Gamma", 0.5, 2.5, self.params.gamma, self.on_slider)
        self.gamma_s.pack(fill="x")

        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Label(sidebar, text="Color Balance", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))

        self.gain_r_s = ModernSlider(sidebar, "Red", 0.7, 1.4, self.params.gain_r, self.on_slider)
        self.gain_r_s.pack(fill="x")
        self.gain_g_s = ModernSlider(sidebar, "Green", 0.7, 1.4, self.params.gain_g, self.on_slider)
        self.gain_g_s.pack(fill="x")
        self.gain_b_s = ModernSlider(sidebar, "Blue", 0.7, 1.4, self.params.gain_b, self.on_slider)
        self.gain_b_s.pack(fill="x")

        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Label(sidebar, text="Crop", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        self.aspect_var = tk.StringVar(value=crop.ASPECT_PRESETS[0][0])
        aspect_box = ttk.Combobox(sidebar, textvariable=self.aspect_var, state="readonly",
                                   values=[label for label, _ in crop.ASPECT_PRESETS])
        aspect_box.pack(fill="x", pady=(0, 8))
        aspect_box.bind("<<ComboboxSelected>>", self.on_aspect_change)
        PillButton(sidebar, "Reset Crop", command=self.reset_crop,
                   bg=theme.PANEL).pack(anchor="w")
        ttk.Label(sidebar, text="Click 'Crop' above, then drag the\ncorner handles or the box itself.",
                  style="Panel.TLabel", justify="left").pack(anchor="w", pady=(8, 0))

        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Label(sidebar, text="Film Base", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        swatch_row = ttk.Frame(sidebar, style="Panel.TFrame")
        swatch_row.pack(fill="x")
        self.base_swatch = tk.Canvas(swatch_row, width=32, height=32, bg=theme.PANEL,
                                      highlightthickness=0)
        self.base_swatch.pack(side="left")
        self.base_lbl = ttk.Label(swatch_row, text="not sampled", style="Panel.TLabel")
        self.base_lbl.pack(side="left", padx=8)
        ttk.Label(sidebar, text="Click anywhere on the image to sample\nthe orange mask from unexposed film.",
                  style="Panel.TLabel", justify="left").pack(anchor="w", pady=(6, 0))

        self._update_base_swatch()

        # status bar
        status = ttk.Frame(self.root, style="Status.TFrame", padding=(10, 4))
        status.pack(side="bottom", fill="x")
        self.status_lbl = ttk.Label(status, text="No image loaded", style="Status.TLabel")
        self.status_lbl.pack(side="left")

    def _bind_shortcuts(self):
        self.root.bind("<Command-o>", lambda e: self.open_image())
        self.root.bind("<Control-o>", lambda e: self.open_image())
        self.root.bind("<Command-s>", lambda e: self.save_image())
        self.root.bind("<Control-s>", lambda e: self.save_image())

    def _center_placeholder(self, _evt=None):
        if self.full_arr is None:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            self.canvas.coords(self.canvas_placeholder, w // 2, h // 2)

    # ---------- image IO ----------

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Open C-41 negative scan",
            filetypes=[
                ("All supported", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.dng"),
                ("Scanner RAW (DNG)", "*.dng"),
                ("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.full_arr, self.is_linear = processor.load_negative(path)
        except Exception as exc:
            messagebox.showerror("Could not open image", str(exc))
            return

        self.image_path = path
        self.preview_arr = processor.downscale(self.full_arr, PREVIEW_MAX_DIM)
        h, w = self.full_arr.shape[:2]
        ph, pw = self.preview_arr.shape[:2]
        self.preview_scale = ph / h

        self.crop_mode = False
        self.crop_btn.set_active(False)
        self.crop_rect = crop.FULL_RECT
        self.aspect_ratio = None
        self.aspect_var.set(crop.ASPECT_PRESETS[0][0])

        self.params.base_color = processor.estimate_base_color(self.preview_arr)
        self._update_base_swatch()
        self.status_lbl.configure(
            text=f"{os.path.basename(path)}  —  {w}×{h}px  —  base color estimated, click image to refine")
        self.render_preview()

    def save_image(self):
        if self.full_arr is None:
            messagebox.showinfo("Nothing to save", "Open a negative first.")
            return
        default_name = "converted.tif"
        if self.image_path:
            base = os.path.splitext(os.path.basename(self.image_path))[0]
            default_name = f"{base}_positive.tif"
        path = filedialog.asksaveasfilename(
            title="Save converted positive",
            initialfile=default_name,
            defaultextension=".tif",
            filetypes=[("TIFF", "*.tif"), ("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not path:
            return
        x0, y0, x1, y1 = crop.crop_pixel_box(self.full_arr.shape, self.crop_rect)
        cropped = self.full_arr[y0:y1, x0:x1]
        full_positive = processor.convert(cropped, self.params, self.is_linear)
        out = Image.fromarray(processor.to_uint8(full_positive))
        try:
            out.save(path)
        except Exception as exc:
            messagebox.showerror("Could not save image", str(exc))
            return
        self.status_lbl.configure(text=f"Saved {os.path.basename(path)}")

    # ---------- processing / rendering ----------

    def on_slider(self):
        self.params.exposure = self.exposure_s.get()
        self.params.contrast = self.contrast_s.get()
        self.params.gamma = self.gamma_s.get()
        self.params.gain_r = self.gain_r_s.get()
        self.params.gain_g = self.gain_g_s.get()
        self.params.gain_b = self.gain_b_s.get()
        self.render_preview()

    def reset_adjustments(self):
        self.params.reset_adjustments()
        self.exposure_s.set(self.params.exposure)
        self.contrast_s.set(self.params.contrast)
        self.gamma_s.set(self.params.gamma)
        self.gain_r_s.set(self.params.gain_r)
        self.gain_g_s.set(self.params.gain_g)
        self.gain_b_s.set(self.params.gain_b)
        self.render_preview()

    def auto_base(self):
        if self.preview_arr is None:
            return
        self.params.base_color = processor.estimate_base_color(self.preview_arr)
        self._update_base_swatch()
        self.render_preview()

    def _update_base_swatch(self):
        r, g, b = (int(np.clip(c, 0, 1) * 255) for c in self.params.base_color)
        self.base_swatch.delete("all")
        widgets.round_rectangle(self.base_swatch, 1, 1, 31, 31, 8,
                                 fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        self.base_lbl.configure(text=f"R{r} G{g} B{b}")

    def render_preview(self):
        if self.preview_arr is None:
            return
        ph, pw = self.preview_arr.shape[:2]
        if self.crop_mode:
            source = self.preview_arr
            origin_px = (0, 0)
        else:
            x0, y0, x1, y1 = crop.crop_pixel_box((ph, pw), self.crop_rect)
            source = self.preview_arr[y0:y1, x0:x1]
            origin_px = (x0, y0)

        positive = processor.convert(source, self.params, self.is_linear)
        img = Image.fromarray(processor.to_uint8(positive))

        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        iw, ih = img.size
        fit = min(cw / iw, ch / ih, 1.0) if (iw > cw or ih > ch) else min(cw / iw, ch / ih)
        disp_w, disp_h = max(1, int(iw * fit)), max(1, int(ih * fit))
        if (disp_w, disp_h) != (iw, ih):
            img = img.resize((disp_w, disp_h), Image.BILINEAR)

        self.tk_image = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        ox = (cw - disp_w) // 2
        oy = (ch - disp_h) // 2
        self._img_offset = (ox, oy)
        self._img_display_scale = disp_w / iw  # relative to `source` pixels
        self._display_origin_px = origin_px    # source's origin within preview_arr
        self.canvas.create_image(ox, oy, anchor="nw", image=self.tk_image, tags=("bg_image",))

        if self.crop_mode:
            self._draw_crop_overlay()

    # ---------- crop tool ----------

    def toggle_crop(self):
        if self.full_arr is None:
            return
        self.crop_mode = not self.crop_mode
        self.crop_btn.set_active(self.crop_mode)
        self.render_preview()

    def reset_crop(self):
        self.crop_rect = crop.FULL_RECT
        self.render_preview()

    def on_aspect_change(self, _evt=None):
        ratio = dict(crop.ASPECT_PRESETS)[self.aspect_var.get()]
        self.aspect_ratio = ratio
        if self.full_arr is not None and ratio is not None:
            H, W = self.full_arr.shape[:2]
            self.crop_rect = crop.fit_rect_to_ratio(self.crop_rect, ratio, W, H)
        self.render_preview()

    def _draw_crop_overlay(self):
        self.canvas.delete("crop_overlay")
        ph, pw = self.preview_arr.shape[:2]
        ox, oy = self._img_offset
        scale = self._img_display_scale
        fx0, fy0, fx1, fy1 = self.crop_rect

        ix0, iy0 = ox, oy
        ix1, iy1 = ox + pw * scale, oy + ph * scale
        cx0, cy0 = ox + fx0 * pw * scale, oy + fy0 * ph * scale
        cx1, cy1 = ox + fx1 * pw * scale, oy + fy1 * ph * scale

        dim = dict(fill=theme.CANVAS_BG, stipple="gray50", outline="", tags=("crop_overlay",))
        self.canvas.create_rectangle(ix0, iy0, ix1, cy0, **dim)  # top
        self.canvas.create_rectangle(ix0, cy1, ix1, iy1, **dim)  # bottom
        self.canvas.create_rectangle(ix0, cy0, cx0, cy1, **dim)  # left
        self.canvas.create_rectangle(cx1, cy0, ix1, cy1, **dim)  # right

        self.canvas.create_rectangle(cx0, cy0, cx1, cy1, outline=theme.ACCENT, width=2,
                                      tags=("crop_overlay",))

        self._crop_handles = {"tl": (cx0, cy0), "tr": (cx1, cy0), "bl": (cx0, cy1), "br": (cx1, cy1)}
        for hx, hy in self._crop_handles.values():
            self.canvas.create_oval(hx - CROP_HANDLE_R, hy - CROP_HANDLE_R,
                                     hx + CROP_HANDLE_R, hy + CROP_HANDLE_R,
                                     fill=theme.HANDLE, outline=theme.ACCENT_DARK, width=2,
                                     tags=("crop_overlay",))
        self._crop_rect_canvas = (cx0, cy0, cx1, cy1)

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

    def on_canvas_press(self, event):
        if self.full_arr is None:
            return
        if self.crop_mode:
            handle = self._hit_test_handle(event.x, event.y)
            if handle:
                self._crop_drag = {"mode": "resize", "corner": handle}
            elif self._point_in_crop_rect(event.x, event.y):
                self._crop_drag = {"mode": "move", "start": (event.x, event.y),
                                    "orig_rect": self.crop_rect}
            else:
                self._crop_drag = None
        else:
            self._sample_base_from_click(event)

    def on_canvas_drag(self, event):
        if not self.crop_mode or self._crop_drag is None or self.preview_arr is None:
            return
        ph, pw = self.preview_arr.shape[:2]
        ox, oy = self._img_offset
        scale = self._img_display_scale
        H, W = self.full_arr.shape[:2]

        fx = min(max((event.x - ox) / scale / pw, 0.0), 1.0)
        fy = min(max((event.y - oy) / scale / ph, 0.0), 1.0)

        if self._crop_drag["mode"] == "move":
            start_x, start_y = self._crop_drag["start"]
            dfx = (event.x - start_x) / scale / pw
            dfy = (event.y - start_y) / scale / ph
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

    def on_canvas_release(self, _event):
        self._crop_drag = None

    def _sample_base_from_click(self, event):
        ox, oy = self._img_offset
        scale = self._img_display_scale
        ox_px, oy_px = self._display_origin_px
        img_x = int(ox_px + (event.x - ox) / scale)
        img_y = int(oy_px + (event.y - oy) / scale)
        ph, pw = self.preview_arr.shape[:2]
        if not (0 <= img_x < pw and 0 <= img_y < ph):
            return
        self.params.base_color = processor.sample_base_color(self.preview_arr, img_x, img_y)
        self._update_base_swatch()
        self.render_preview()


def main():
    root = tk.Tk()
    NegConvertApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
