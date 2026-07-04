"""Tkinter UI for NegConvert."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageTk

from . import processor
from . import theme

PREVIEW_MAX_DIM = 900


class Slider(ttk.Frame):
    """A labeled slider with a live value readout, on the panel background."""

    def __init__(self, parent, label, frm, to, initial, step, on_change):
        super().__init__(parent, style="Panel.TFrame")
        self._on_change = on_change

        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=label, style="Panel.TLabel").pack(side="left")
        self.value_lbl = ttk.Label(header, text=f"{initial:.2f}", style="Value.TLabel")
        self.value_lbl.pack(side="right")

        self.var = tk.DoubleVar(value=initial)
        self.scale = ttk.Scale(self, from_=frm, to=to, orient="horizontal",
                                variable=self.var, command=self._changed)
        self.scale.pack(fill="x", pady=(2, 10))
        self._step = step

    def _changed(self, _evt):
        self.value_lbl.configure(text=f"{self.var.get():.2f}")
        self._on_change()

    def get(self):
        return self.var.get()

    def set(self, value):
        self.var.set(value)
        self.value_lbl.configure(text=f"{value:.2f}")


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
        self.tk_image = None
        self.image_path = None

        self._build_layout()
        self._bind_shortcuts()

    # ---------- layout ----------

    def _build_layout(self):
        toolbar = ttk.Frame(self.root, style="Panel.TFrame", padding=8)
        toolbar.pack(side="top", fill="x")

        ttk.Button(toolbar, text="Open Negative…", command=self.open_image).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Auto Base Color", command=self.auto_base).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Reset Adjustments", command=self.reset_adjustments).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save As…", style="Accent.TButton",
                   command=self.save_image).pack(side="right", padx=4)

        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)

        # canvas / preview area
        canvas_frame = ttk.Frame(body)
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=theme.CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas_placeholder = self.canvas.create_text(
            0, 0, text="Open a negative scan to begin\n(click the image later to sample the film base color)",
            fill=theme.TEXT_DIM, font=("Helvetica", 13), justify="center")
        self.canvas.bind("<Configure>", self._center_placeholder)

        # sidebar
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=14, width=280)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Adjustments", style="Heading.TLabel").pack(anchor="w", pady=(0, 10))

        self.exposure_s = Slider(sidebar, "Exposure", 0.2, 3.0, self.params.exposure, 0.01, self.on_slider)
        self.exposure_s.pack(fill="x")
        self.contrast_s = Slider(sidebar, "Contrast", 0.5, 3.0, self.params.contrast, 0.01, self.on_slider)
        self.contrast_s.pack(fill="x")
        self.gamma_s = Slider(sidebar, "Gamma", 0.5, 4.0, self.params.gamma, 0.01, self.on_slider)
        self.gamma_s.pack(fill="x")

        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Label(sidebar, text="White Balance Trim", style="Heading.TLabel").pack(anchor="w", pady=(0, 10))

        self.gain_r_s = Slider(sidebar, "Red", 0.5, 1.5, self.params.gain_r, 0.01, self.on_slider)
        self.gain_r_s.pack(fill="x")
        self.gain_g_s = Slider(sidebar, "Green", 0.5, 1.5, self.params.gain_g, 0.01, self.on_slider)
        self.gain_g_s.pack(fill="x")
        self.gain_b_s = Slider(sidebar, "Blue", 0.5, 1.5, self.params.gain_b, 0.01, self.on_slider)
        self.gain_b_s.pack(fill="x")

        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Label(sidebar, text="Film Base", style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        swatch_row = ttk.Frame(sidebar, style="Panel.TFrame")
        swatch_row.pack(fill="x")
        self.base_swatch = tk.Canvas(swatch_row, width=28, height=28, highlightthickness=1,
                                      highlightbackground=theme.PANEL_DARK)
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
            self.full_arr = processor.load_negative(path)
        except Exception as exc:
            messagebox.showerror("Could not open image", str(exc))
            return

        self.image_path = path
        self.preview_arr = processor.downscale(self.full_arr, PREVIEW_MAX_DIM)
        h, w = self.full_arr.shape[:2]
        ph, pw = self.preview_arr.shape[:2]
        self.preview_scale = ph / h

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
        full_positive = processor.convert(self.full_arr, self.params)
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
        self.base_swatch.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
        self.base_lbl.configure(text=f"R{r} G{g} B{b}")

    def render_preview(self):
        if self.preview_arr is None:
            return
        positive = processor.convert(self.preview_arr, self.params)
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
        self._img_display_scale = disp_w / iw  # relative to preview_arr pixels
        self.canvas.create_image(ox, oy, anchor="nw", image=self.tk_image)

    def on_canvas_click(self, event):
        if self.full_arr is None:
            return
        ox, oy = getattr(self, "_img_offset", (0, 0))
        scale = getattr(self, "_img_display_scale", 1.0)
        img_x = int((event.x - ox) / scale)
        img_y = int((event.y - oy) / scale)
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
