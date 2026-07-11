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
from .widgets import Filmstrip, Histogram, ModernSlider, PillButton, PipetteButton, TabBar

PREVIEW_MAX_DIM = 900
HANDLE_HIT_RADIUS = 12
CROP_HANDLE_R = 8
TAB_COLORS, TAB_ADJUST, TAB_CROP, TAB_EXPORT = 0, 1, 2, 3
STRAIGHTEN_GUIDE_COUNT = 10
STRAIGHTEN_GUIDE_COLOR = "#ff3b30"

# Right-click-selectable background behind the displayed image, so you can
# judge exposure/contrast against different surround tones.
FRAME_COLORS = [("White", "#ffffff"), ("Middle Grey", "#808080"), ("Dark Grey", "#333333")]
FRAME_BORDER_COLOR = "#555555"
DEFAULT_FRAME_COLOR = "#808080"
IMAGE_FIT_SCALE = 0.9  # image fills this fraction of the available space; the rest is the frame margin


class PhotoItem:
    """Per-photo editing state, so each photo opened via 'Open Folder…' can
    be adjusted independently. `full_arr`/`preview_arr` are loaded lazily -
    only when the photo is first selected - so opening a folder of many
    large DNGs doesn't decode all of them up front."""

    def __init__(self, path):
        self.path = path
        self.full_arr = None
        self.preview_arr = None
        self.is_linear = False
        self.loaded = False
        self.params = processor.Params()
        self.crop_rect = crop.FULL_RECT
        self.aspect_ratio = None
        self.rotation_90 = 0        # quarter turns clockwise (0-3)
        self.straighten_angle = 0.0  # fine angle, degrees clockwise
        self.auto_baseline = (0.0, 1.0, 1.0)  # (exposure, contrast, gamma) from this photo's first auto-level


class NegConvertApp:
    EXPORT_FORMATS = [("TIFF", "tif"), ("PNG", "png"), ("JPEG", "jpg"), ("Linear DNG", "dng")]

    def __init__(self, root):
        self.root = root
        self.root.title("NegConvert — C-41 Negative Converter")
        self.root.geometry("1280x820")
        self._set_window_icon()
        theme.apply(root)

        self.params = processor.Params()
        self.full_arr = None       # full resolution negative, float32 0..1
        self.preview_arr = None    # downscaled negative for interactive preview
        self.is_linear = False     # True for raw/DNG sources (no sRGB gamma)
        self.tk_image = None
        self.image_path = None
        self.frame_bg_color = DEFAULT_FRAME_COLOR

        self.crop_mode = False
        self.crop_rect = crop.FULL_RECT     # (fx0, fy0, fx1, fy1), fractional of full image
        self.aspect_ratio = None            # None = Free
        self.rotation_90 = 0                 # quarter turns clockwise (0-3)
        self.straighten_angle = 0.0          # fine angle, degrees clockwise
        self._working_arr = None            # preview_arr with rotation applied, cached per render
        self._show_straighten_guides = False  # horizontal reference lines, shown only while dragging
        self._crop_drag = None
        self._crop_handles = {}
        self._crop_rect_canvas = None

        self.zoom_100 = False           # False = fit to window, True = 1 full-res pixel per screen-pixel
        self._zoom_center = (0.5, 0.5)  # fractional (x, y) within the crop, set by double-click
        self._sample_arr = None         # whichever array is currently on screen; see _sample_base_from_click
        self.pipette_active = False  # armed by the Film Base pipette button; makes the next canvas
                                      # click sample the base color instead of doing nothing

        self.photos = []              # list of PhotoItem, for batch (Open Folder) editing
        self.current_photo_index = -1

        self._build_layout()
        self._bind_shortcuts()

    def _set_window_icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon_1024.png")
        try:
            self._icon_image = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon_image)
        except tk.TclError:
            pass  # packaged .app builds get their icon from NegConvert.spec instead

    # ---------- layout ----------

    def _build_layout(self):
        toolbar = ttk.Frame(self.root, style="Panel.TFrame", padding=12)
        toolbar.pack(side="top", fill="x")

        PillButton(toolbar, "Open Negative…", command=self.open_image,
                   bg=theme.PANEL).pack(side="left", padx=4)
        PillButton(toolbar, "Open Folder…", command=self.open_folder,
                   bg=theme.PANEL).pack(side="left", padx=4)
        PillButton(toolbar, "Auto Base Color", command=self.auto_base,
                   bg=theme.PANEL).pack(side="left", padx=4)
        PillButton(toolbar, "Reset Adjustments", command=self.reset_adjustments,
                   bg=theme.PANEL).pack(side="left", padx=4)

        # status bar and filmstrip claim the bottom first, so the body
        # (canvas + sidebar) gets whatever space remains between them.
        status = ttk.Frame(self.root, style="Status.TFrame", padding=(10, 4))
        status.pack(side="bottom", fill="x")
        self.status_lbl = ttk.Label(status, text="No image loaded", style="Status.TLabel")
        self.status_lbl.pack(side="left")

        self.filmstrip = Filmstrip(self.root, on_select=self._select_photo,
                                    on_mark_change=self._on_marks_changed)
        self.filmstrip.pack(side="bottom", fill="x")

        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)

        # canvas / preview area
        canvas_frame = ttk.Frame(body)
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=self.frame_bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        # Right-click: bind both Button-2 and Button-3 since which one fires
        # for a "right click" varies by platform/mouse/trackpad setup.
        self.canvas.bind("<Button-2>", self._show_frame_menu)
        self.canvas.bind("<Button-3>", self._show_frame_menu)
        self.canvas_placeholder = self.canvas.create_text(
            0, 0, text="Open a negative scan (or a folder of them) to begin\n"
                       "(click the image later to sample the film base color)",
            fill=self._placeholder_text_color(), font=("Helvetica", 13), justify="center")
        self.canvas.bind("<Configure>", self._center_placeholder)

        # sidebar: histogram (upper) + tabbed controls (lower)
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=12, width=380)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Histogram", style="Heading.TLabel").pack(anchor="w", pady=(0, 10))
        self.histogram = Histogram(sidebar, height=120)
        self.histogram.pack(fill="x", pady=(0, 16))

        ttk.Separator(sidebar).pack(fill="x", pady=(0, 14))

        self.tab_bar = TabBar(sidebar, ["Colors", "Adjustments", "Crop", "Export"], on_change=self.on_tab_changed)
        self.tab_bar.pack(fill="x", pady=(0, 14))

        tab_content = ttk.Frame(sidebar, style="Panel.TFrame")
        tab_content.pack(fill="both", expand=True)

        adjust_tab = ttk.Frame(tab_content, style="Panel.TFrame", padding=(6, 4))
        colors_tab = ttk.Frame(tab_content, style="Panel.TFrame", padding=(6, 4))
        crop_tab = ttk.Frame(tab_content, style="Panel.TFrame", padding=(6, 4))
        export_tab = ttk.Frame(tab_content, style="Panel.TFrame", padding=(6, 4))
        for frame in (adjust_tab, colors_tab, crop_tab, export_tab):
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._tab_frames = [colors_tab, adjust_tab, crop_tab, export_tab]

        self._build_adjustments_tab(adjust_tab)
        self._build_colors_tab(colors_tab)
        self._build_crop_tab(crop_tab)
        self._build_export_tab(export_tab)
        adjust_tab.tkraise()

    def _build_adjustments_tab(self, parent):
        self.exposure_s = ModernSlider(parent, "Exposure (EV)", -8.0, 8.0, self.params.exposure, self.on_slider,
                                        default=0.0)
        self.exposure_s.pack(fill="x")
        self.density_s = ModernSlider(parent, "Density", -4.0, 4.0, self.params.density, self.on_slider,
                                       default=0.0)
        self.density_s.pack(fill="x")
        self.shadow_density_s = ModernSlider(parent, "Shadow Density", -2.0, 2.0,
                                              self.params.shadow_density, self.on_slider, default=0.0)
        self.shadow_density_s.pack(fill="x")
        self.highlight_density_s = ModernSlider(parent, "Highlight Density", -2.0, 2.0,
                                                 self.params.highlight_density, self.on_slider, default=0.0)
        self.highlight_density_s.pack(fill="x")
        self.contrast_s = ModernSlider(parent, "Contrast", 0.5, 2.5, self.params.contrast, self.on_slider,
                                        default=1.0)
        self.contrast_s.pack(fill="x")
        self.gamma_s = ModernSlider(parent, "Gamma", 0.3, 2.5, self.params.gamma, self.on_slider,
                                     default=1.0)
        self.gamma_s.pack(fill="x")
        self.saturation_s = ModernSlider(parent, "Saturation", 0.0, 2.0, self.params.saturation, self.on_slider,
                                          default=1.0)
        self.saturation_s.pack(fill="x")
        self.denoise_s = ModernSlider(parent, "Denoise", 0.0, 2.0, self.params.denoise, self.on_slider,
                                       default=0.0)
        self.denoise_s.pack(fill="x")
        self.sharpen_s = ModernSlider(parent, "Sharpening", 0.0, 2.0, self.params.sharpen, self.on_slider,
                                       default=0.0)
        self.sharpen_s.pack(fill="x")

    def _build_colors_tab(self, parent):
        ttk.Label(parent, text="Color Balance", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))

        self.shift_r_s = ModernSlider(parent, "Red", -0.5, 0.5, self.params.shift_r, self.on_slider, default=0.0)
        self.shift_r_s.pack(fill="x")
        self.shift_g_s = ModernSlider(parent, "Green", -0.5, 0.5, self.params.shift_g, self.on_slider, default=0.0)
        self.shift_g_s.pack(fill="x")
        self.shift_b_s = ModernSlider(parent, "Blue", -0.5, 0.5, self.params.shift_b, self.on_slider, default=0.0)
        self.shift_b_s.pack(fill="x")

        ttk.Separator(parent).pack(fill="x", pady=4)
        ttk.Label(parent, text="Film Base", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
        swatch_row = ttk.Frame(parent, style="Panel.TFrame")
        swatch_row.pack(fill="x")
        self.pipette_btn = PipetteButton(swatch_row, command=self._on_pipette_toggle, bg=theme.PANEL)
        self.pipette_btn.pack(side="left")
        self.base_swatch = tk.Canvas(swatch_row, width=32, height=32, bg=theme.PANEL,
                                      highlightthickness=0)
        self.base_swatch.pack(side="left", padx=(8, 0))
        self.base_lbl = ttk.Label(swatch_row, text="not sampled", style="Panel.TLabel")
        self.base_lbl.pack(side="left", padx=8)
        ttk.Label(parent, text="Click the pipette, then click anywhere on\n"
                               "the image to sample the orange mask from\n"
                               "unexposed film.",
                  style="Panel.TLabel", justify="left").pack(anchor="w", pady=(3, 0))

        self._update_base_swatch()

    def _build_crop_tab(self, parent):
        ttk.Label(parent, text="Crop", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        self.aspect_var = tk.StringVar(value=crop.ASPECT_PRESETS[0][0])
        aspect_box = ttk.Combobox(parent, textvariable=self.aspect_var, state="readonly",
                                   values=[label for label, _ in crop.ASPECT_PRESETS])
        aspect_box.pack(fill="x", pady=(0, 8))
        aspect_box.bind("<<ComboboxSelected>>", self.on_aspect_change)
        PillButton(parent, "Reset Crop", command=self.reset_crop,
                   bg=theme.PANEL).pack(anchor="w")
        ttk.Label(parent, text="While this tab is open, drag the corner\n"
                               "handles or the box itself on the image.\n"
                               "Switch tabs to preview the cropped result.",
                  style="Panel.TLabel", justify="left").pack(anchor="w", pady=(8, 0))

        ttk.Separator(parent).pack(fill="x", pady=8)
        ttk.Label(parent, text="Rotate", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        rotate_row = ttk.Frame(parent, style="Panel.TFrame")
        rotate_row.pack(fill="x", pady=(0, 4))
        PillButton(rotate_row, "Rotate Left", command=self.rotate_left,
                   bg=theme.PANEL).pack(side="left", padx=(0, 6))
        PillButton(rotate_row, "Rotate Right", command=self.rotate_right,
                   bg=theme.PANEL).pack(side="left")
        self.straighten_s = ModernSlider(parent, "Straighten (°)", -45.0, 45.0,
                                          self.straighten_angle, self.on_straighten_change, default=0.0)
        self.straighten_s.pack(fill="x")
        # add=True: layer on top of ModernSlider's own press/drag bindings
        # rather than replacing them, so the slider still works normally.
        self.straighten_s.canvas.bind("<ButtonPress-1>", self._on_straighten_drag_start, add="+")
        self.straighten_s.canvas.bind("<ButtonRelease-1>", self._on_straighten_drag_end, add="+")

    def _build_export_tab(self, parent):
        ttk.Label(parent, text="Export", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(parent, text="Save the converted positive - with any\n"
                               "crop currently set - as DNG, TIFF, PNG, or JPEG.",
                  style="Panel.TLabel", justify="left").pack(anchor="w", pady=(0, 14))

        ttk.Label(parent, text="Format", style="Panel.TLabel").pack(anchor="w")
        self.export_format_var = tk.StringVar(value=self.EXPORT_FORMATS[0][0])
        format_box = ttk.Combobox(parent, textvariable=self.export_format_var, state="readonly",
                                   values=[label for label, _ in self.EXPORT_FORMATS])
        format_box.pack(fill="x", pady=(2, 10))
        format_box.bind("<<ComboboxSelected>>", self._on_export_format_change)

        ttk.Label(parent, text="Color Profile", style="Panel.TLabel").pack(anchor="w")
        self.export_profile_var = tk.StringVar(value=processor.COLOR_PROFILES[0])
        self.profile_box = ttk.Combobox(parent, textvariable=self.export_profile_var, state="readonly",
                                         values=processor.COLOR_PROFILES)
        self.profile_box.pack(fill="x", pady=(2, 4))
        self.profile_hint_lbl = ttk.Label(parent, text="", style="Status.TLabel", justify="left")
        self.profile_hint_lbl.pack(anchor="w", pady=(0, 14))

        PillButton(parent, "Save As…", command=self.save_image, accent=True,
                   font=("Helvetica", 11, "bold")).pack(anchor="w")

        ttk.Separator(parent).pack(fill="x", pady=14)

        ttk.Label(parent, text="Batch Export", style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        self.marked_lbl = ttk.Label(
            parent, text="Ctrl+click photos in the filmstrip\nto select several for batch export.",
            style="Panel.TLabel", justify="left")
        self.marked_lbl.pack(anchor="w", pady=(0, 8))
        PillButton(parent, "Export Selected…", command=self.export_selected,
                   bg=theme.PANEL).pack(anchor="w")

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

    def _placeholder_text_color(self):
        return "#2b2b2b" if self.frame_bg_color == "#ffffff" else theme.TEXT_DIM

    def _show_frame_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, bg=theme.PANEL_DARK, fg=theme.TEXT,
                        activebackground=theme.ACCENT, activeforeground="#2b2b2b")
        for label, color in FRAME_COLORS:
            menu.add_command(label=label, command=lambda c=color: self._set_frame_color(c))
        menu.tk_popup(event.x_root, event.y_root)

    def _set_frame_color(self, color):
        self.frame_bg_color = color
        self.canvas.configure(bg=color)
        self.canvas.itemconfig(self.canvas_placeholder, fill=self._placeholder_text_color())
        self.render_preview()

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
        self._load_photo_list([path])

    def open_folder(self):
        folder = filedialog.askdirectory(title="Open folder of negative scans")
        if not folder:
            return
        paths = sorted(
            os.path.join(folder, name) for name in os.listdir(folder)
            if os.path.splitext(name)[1].lower() in processor.IMAGE_EXTENSIONS
        )
        if not paths:
            messagebox.showinfo("No images found",
                                 "That folder has no supported image files (JPG/PNG/TIFF/BMP/DNG).")
            return
        self._load_photo_list(paths)

    def _load_photo_list(self, paths):
        """Start a new editing session over one or more photos, each with
        its own independent adjustments (see PhotoItem). Thumbnails are
        generated up front (fast - they read each file's embedded preview
        rather than fully decoding it); the actual pixel data for each
        photo is only decoded the first time it's selected."""
        self.photos = [PhotoItem(p) for p in paths]
        self.current_photo_index = -1
        thumbs = [(item.path, processor.extract_thumbnail(item.path)) for item in self.photos]
        self.filmstrip.set_photos(thumbs)
        self._select_photo(0)

    def _select_photo(self, index):
        if not (0 <= index < len(self.photos)) or index == self.current_photo_index:
            return

        # the outgoing photo's crop/aspect are plain tuples (reassigned, not
        # mutated in place) so they need to be written back explicitly;
        # `params` is a mutable object the PhotoItem already shares a
        # reference to, so it's implicitly kept in sync as sliders change it -
        # this copy is just cheap insurance against that assumption changing.
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
        self.tab_bar.select(TAB_ADJUST)
        self._tab_frames[TAB_ADJUST].tkraise()

        self._sync_controls_from_state(item)
        self.filmstrip.set_selected(index)

        h, w = self.full_arr.shape[:2]
        total = len(self.photos)
        label = os.path.basename(item.path) if total == 1 else f"{os.path.basename(item.path)} ({index + 1}/{total})"
        self.status_lbl.configure(text=f"{label}  —  {w}×{h}px")

        self.render_preview()

    def _ensure_photo_loaded(self, item):
        """Lazily decode a PhotoItem's full-res pixel data and compute its
        initial auto base-color/levels, the first time it's touched (either
        by selecting it in the filmstrip or exporting it while marked but
        never visited). Returns False (after showing an error) on failure."""
        if item.loaded:
            return True
        try:
            item.full_arr, item.is_linear = processor.load_negative(item.path)
        except Exception as exc:
            messagebox.showerror("Could not open image", f"{os.path.basename(item.path)}: {exc}")
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
        """Push the newly-selected photo's params/crop onto every control,
        so switching photos in the filmstrip shows that photo's own edits
        (not whatever the previous photo's sliders happened to show)."""
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
        self.aspect_var.set(label)
        self.straighten_s.set(self.straighten_angle)

    def _on_export_format_change(self, event=None):
        ext = dict(self.EXPORT_FORMATS)[self.export_format_var.get()]
        if ext == "dng":
            self.profile_box.configure(state="disabled")
            self.profile_hint_lbl.configure(text="Linear DNG is raw data - no color\nprofile is embedded.")
        else:
            self.profile_box.configure(state="readonly")
            self.profile_hint_lbl.configure(text="")

    def _on_marks_changed(self, marked):
        n = len(marked)
        if n == 0:
            text = "Ctrl+click photos in the filmstrip\nto select several for batch export."
        elif n == 1:
            text = "1 photo selected for batch export."
        else:
            text = f"{n} photos selected for batch export."
        self.marked_lbl.configure(text=text)

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
            messagebox.showinfo("Nothing to save", "Open a negative first.")
            return
        ext = dict(self.EXPORT_FORMATS)[self.export_format_var.get()]
        profile_name = self.export_profile_var.get()
        default_name = f"converted.{ext}"
        if self.image_path:
            base = os.path.splitext(os.path.basename(self.image_path))[0]
            default_name = f"{base}_positive.{ext}"
        filetypes = {
            "tif": [("TIFF", "*.tif")],
            "png": [("PNG", "*.png")],
            "jpg": [("JPEG", "*.jpg")],
            "dng": [("Linear DNG (raw-editable)", "*.dng")],
        }[ext]
        path = filedialog.asksaveasfilename(
            title="Save converted positive",
            initialfile=default_name,
            defaultextension=f".{ext}",
            filetypes=filetypes,
        )
        if not path:
            return
        try:
            self._convert_and_save_one(self.full_arr, self.is_linear, self.params, self.crop_rect,
                                        self.rotation_90, self.straighten_angle, path, ext, profile_name)
        except Exception as exc:
            messagebox.showerror("Could not save image", str(exc))
            return
        self.status_lbl.configure(text=f"Saved {os.path.basename(path)}")

    def export_selected(self):
        marked = sorted(self.filmstrip.get_marked())
        if not marked:
            messagebox.showinfo("Nothing selected",
                                 "Ctrl+click two or more photos in the filmstrip first.")
            return
        folder = filedialog.askdirectory(title="Choose a folder for the exported photos")
        if not folder:
            return
        ext = dict(self.EXPORT_FORMATS)[self.export_format_var.get()]
        profile_name = self.export_profile_var.get()

        # the active photo's in-memory params/crop can be ahead of what's
        # stored on its PhotoItem - that's only written back when switching
        # away, in _select_photo - so refresh it before reading self.photos.
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
            messagebox.showerror("Some exports failed",
                                  f"Saved {saved} of {len(marked)}.\n\nFailed:\n" + "\n".join(failed))
        else:
            self.status_lbl.configure(
                text=f"Exported {saved} photo{'s' if saved != 1 else ''} to {os.path.basename(folder)}")

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
        self.params.base_color = processor.estimate_base_color(self.preview_arr)
        self._update_base_swatch()
        self._apply_auto_levels()

    def _apply_auto_levels(self):
        """Recompute Exposure/Contrast/Gamma so this image's own density
        histogram maps sensibly onto the output range, correcting for
        however far off the base color estimate happens to be and for
        however skewed this scene's own tonal distribution is
        (see processor.auto_levels).

        Also re-baselines what a double-click on those three sliders resets
        to, so "reset" means "back to the auto-leveled result for this base
        color sample" rather than a fixed neutral value."""
        if self.preview_arr is None:
            self.render_preview()
            return
        exposure, contrast, gamma = processor.auto_levels(self.preview_arr, self.params.base_color, self.is_linear)
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
        self.base_swatch.delete("all")
        widgets.round_rectangle(self.base_swatch, 1, 1, 31, 31, 8,
                                 fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        self.base_lbl.configure(text=f"R{r} G{g} B{b}")

    def render_preview(self):
        if self.preview_arr is None:
            return
        if self.zoom_100 and not self.crop_mode and self.full_arr is not None:
            self._render_preview_zoomed()
        else:
            self._render_preview_fit()

    def _render_preview_fit(self):
        """Default view: the whole (cropped) image resized to fit the
        canvas - using the downscaled interactive preview, not the full-res
        original, since re-converting the full negative on every slider
        tweak would be far too slow."""
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

        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        iw, ih = img.size
        fit = min(cw / iw, ch / ih, 1.0) if (iw > cw or ih > ch) else min(cw / iw, ch / ih)
        fit *= IMAGE_FIT_SCALE  # shrink so a margin remains on all sides for the frame
        disp_w, disp_h = max(1, int(iw * fit)), max(1, int(ih * fit))
        if (disp_w, disp_h) != (iw, ih):
            img = img.resize((disp_w, disp_h), Image.BILINEAR)

        self._sample_arr = working
        self._place_rendered_image(img, disp_w / iw, origin_px)

        if self.crop_mode:
            self._draw_crop_overlay()

    def _render_preview_zoomed(self):
        """100% view: a canvas-sized window cropped straight out of the
        *full-resolution* negative (not the downscaled preview), centered on
        wherever was last double-clicked, and displayed with no resampling -
        one source pixel per screen pixel. This is what actually makes it a
        "zoom in" from the fit view rather than just a resize: the fit view
        can end up upscaling a small preview to fill the canvas, so showing
        the preview at its own native size can be *smaller*, not bigger,
        which is the wrong direction for a "zoom to 100%" action."""
        working_full = self._apply_rotation(self.full_arr)
        H, W = working_full.shape[:2]
        x0, y0, x1, y1 = crop.crop_pixel_box((H, W), self.crop_rect)
        cropped_full = working_full[y0:y1, x0:x1]
        full_h, full_w = cropped_full.shape[:2]

        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        win_w, win_h = min(cw, full_w), min(ch, full_h)

        cx = int(self._zoom_center[0] * full_w)
        cy = int(self._zoom_center[1] * full_h)
        wx0 = int(np.clip(cx - win_w // 2, 0, max(0, full_w - win_w)))
        wy0 = int(np.clip(cy - win_h // 2, 0, max(0, full_h - win_h)))
        window = cropped_full[wy0:wy0 + win_h, wx0:wx0 + win_w]

        positive = processor.convert(window, self.params, self.is_linear)
        positive_uint8 = processor.to_uint8(positive)
        img = Image.fromarray(positive_uint8)
        self.histogram.update_image(positive_uint8)

        self._sample_arr = window
        self._place_rendered_image(img, 1.0, (0, 0))

    def _place_rendered_image(self, img, display_scale, origin_px):
        """Shared tail of both preview renderers: size the canvas, paint the
        frame background, and draw the image centered with a border.
        `display_scale` and `origin_px` describe how screen coordinates map
        back onto `self._sample_arr` (see `_sample_base_from_click`)."""
        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        disp_w, disp_h = img.size

        self.tk_image = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        # Explicitly repaint the whole canvas rather than relying on the
        # widget's own background: when the displayed image shrinks between
        # renders (e.g. after cropping), the just-vacated area sometimes
        # isn't fully repainted on its own, leaving a faint stale outline
        # where the previous, larger image used to be.
        self.canvas.create_rectangle(0, 0, cw, ch, fill=self.frame_bg_color, outline="", tags=("bg_fill",))
        ox = (cw - disp_w) // 2
        oy = (ch - disp_h) // 2
        self._img_offset = (ox, oy)
        self._img_display_scale = display_scale  # relative to `self._sample_arr` pixels
        self._display_origin_px = origin_px       # `self._sample_arr`'s origin within its source array
        self.canvas.create_image(ox, oy, anchor="nw", image=self.tk_image, tags=("bg_image",))
        self.canvas.create_rectangle(ox, oy, ox + disp_w, oy + disp_h,
                                      outline=FRAME_BORDER_COLOR, width=2, tags=("bg_image",))

    # ---------- crop tool ----------

    def on_tab_changed(self, index):
        self._tab_frames[index].tkraise()
        if index != TAB_COLORS:
            self._set_pipette_active(False)
        if self.full_arr is None:
            return
        is_crop_tab = index == TAB_CROP
        if is_crop_tab != self.crop_mode:
            self.crop_mode = is_crop_tab
            self.render_preview()

    def reset_crop(self):
        self.crop_rect = crop.FULL_RECT
        self.rotation_90 = 0
        self.straighten_angle = 0.0
        self.straighten_s.set(0.0)
        self.render_preview()

    def on_aspect_change(self, _evt=None):
        ratio = dict(crop.ASPECT_PRESETS)[self.aspect_var.get()]
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
        # Only auto-apply the "no empty corners" crop suggestion while the
        # crop is still untouched (full frame). Once the user has set their
        # own crop - by dragging, or from an earlier straighten suggestion -
        # leave it alone; continuously overwriting it on every further
        # straighten tweak would silently throw away their framing.
        if self.full_arr is not None and self.crop_rect == crop.FULL_RECT:
            h, w = self._working_full_dims()
            self.crop_rect = crop.safe_crop_for_straighten(self.straighten_angle, w, h)
        self.render_preview()

    def _on_straighten_drag_start(self, _event=None):
        self._show_straighten_guides = True
        if self.crop_mode:
            self._draw_crop_overlay()

    def _on_straighten_drag_end(self, _event=None):
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
        """Full-resolution (height, width) after the 90°-quarter rotation
        (which swaps dimensions on odd counts); the fine straighten angle
        keeps the canvas size fixed, so it doesn't affect this."""
        h, w = self.full_arr.shape[:2]
        if self.rotation_90 % 2 == 1:
            h, w = w, h
        return h, w

    def _draw_crop_overlay(self):
        self.canvas.delete("crop_overlay")
        ph, pw = self._working_arr.shape[:2]
        ox, oy = self._img_offset
        scale = self._img_display_scale
        fx0, fy0, fx1, fy1 = self.crop_rect

        ix0, iy0 = ox, oy
        ix1, iy1 = ox + pw * scale, oy + ph * scale
        cx0, cy0 = ox + fx0 * pw * scale, oy + fy0 * ph * scale
        cx1, cy1 = ox + fx1 * pw * scale, oy + fy1 * ph * scale

        # Solid fill, not stippled: a dithered/semi-transparent overlay would
        # let faint traces of the excluded full-image content (e.g. an
        # unmasked sliver at the scan's edge) bleed through instead of
        # being fully hidden by the crop-mode "excluded area" look.
        dim = dict(fill=self.frame_bg_color, outline="", tags=("crop_overlay",))
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

        if self._show_straighten_guides:
            for i in range(1, STRAIGHTEN_GUIDE_COUNT + 1):
                gy = iy0 + (i / (STRAIGHTEN_GUIDE_COUNT + 1)) * (iy1 - iy0)
                self.canvas.create_line(ix0, gy, ix1, gy, fill=STRAIGHTEN_GUIDE_COLOR,
                                         width=1, dash=(4, 3), tags=("crop_overlay",))

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
        elif self.pipette_active:
            self._sample_base_from_click(event)
            # stays armed - switching tabs away from Colors, or clicking the
            # pipette button again, is what disarms it, so several spots can
            # be sampled in a row without re-arming each time.
        # else: a plain click on the image does nothing.

    def on_canvas_double_click(self, event):
        if self.full_arr is None or self.crop_mode:
            return
        if not self.zoom_100:
            # Re-center the zoom on wherever was just double-clicked, in
            # fractional (crop-relative) coordinates - resolution-independent,
            # so the same fraction lands on the same spot whether it's read
            # against the downscaled preview (fit view) or the full-res
            # image (zoomed view).
            ox, oy = self._img_offset
            scale = self._img_display_scale
            ox_px, oy_px = self._display_origin_px
            img_x = ox_px + (event.x - ox) / scale
            img_y = oy_px + (event.y - oy) / scale
            ph, pw = self._working_arr.shape[:2]
            x0, y0, x1, y1 = crop.crop_pixel_box((ph, pw), self.crop_rect)
            crop_w, crop_h = max(x1 - x0, 1), max(y1 - y0, 1)
            fx = float(np.clip((img_x - x0) / crop_w, 0.0, 1.0))
            fy = float(np.clip((img_y - y0) / crop_h, 0.0, 1.0))
            self._zoom_center = (fx, fy)
        self.zoom_100 = not self.zoom_100
        self.render_preview()

    def _on_pipette_toggle(self, active):
        self.pipette_active = active
        self.canvas.configure(cursor="crosshair" if active else "")

    def _set_pipette_active(self, active):
        if self.pipette_active == active:
            return
        self.pipette_active = active
        self.pipette_btn.set_active(active)
        self.canvas.configure(cursor="crosshair" if active else "")

    def on_canvas_drag(self, event):
        if not self.crop_mode or self._crop_drag is None or self._working_arr is None:
            return
        ph, pw = self._working_arr.shape[:2]
        ox, oy = self._img_offset
        scale = self._img_display_scale
        H, W = self._working_full_dims()

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
        if self._sample_arr is None:
            return
        ox, oy = self._img_offset
        scale = self._img_display_scale
        ox_px, oy_px = self._display_origin_px
        img_x = int(ox_px + (event.x - ox) / scale)
        img_y = int(oy_px + (event.y - oy) / scale)
        ph, pw = self._sample_arr.shape[:2]
        if not (0 <= img_x < pw and 0 <= img_y < ph):
            return
        self.params.base_color = processor.sample_base_color(self._sample_arr, img_x, img_y)
        self._update_base_swatch()
        self._apply_auto_levels()


def main():
    root = tk.Tk()
    NegConvertApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
