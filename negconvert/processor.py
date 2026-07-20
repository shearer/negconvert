"""Core negative/slide -> positive conversion math.

Film density is a linear-light, logarithmic phenomenon: doubling the light
that hit the film adds a fixed increment of dye density, and density is
what attenuates the scanner's light source. So the conversion has to happen
in *linear* light, using a *log* (density) relationship - not a ratio/
subtraction done directly on gamma-encoded pixel values, which distorts
color balance across shadows and highlights.

Pipeline:
1. Linearize the scan (undo sRGB gamma) - unless it's already linear (DNG).
2. Divide by the (linearized) sampled film-base color to neutralize the
   orange mask, then take -log2 of that ratio to get a density image
   (0 at the film base, increasing with exposure). E-6 slides are already
   a positive image, not a dye-masked negative, so that step flips sign
   instead (density grows with scan *brightness*, not darkness).
3. Apply per-channel density gain (color balance), an exposure shift, and
   a contrast scale - all in density/stops space.
4. Map density back to a displayable 0..1 range, apply a gamma trim, and
   re-encode to sRGB for viewing/saving. B&W collapses to neutral gray here.
"""
import io
import os
from dataclasses import dataclass

import numpy as np
from PIL import Image

EPS = 1e-6
# .dng covers both scanner-style Linear DNGs and camera DNGs; the rest are
# native camera raw formats, read through the same rawpy/libraw path (see
# _load_raw_file) - libraw identifies the actual format from file content,
# not the extension, so this set only needs to make the files selectable.
RAW_EXTENSIONS = {
    ".dng",
    ".cr2", ".cr3",           # Canon
    ".nef", ".nrw",           # Nikon
    ".arw", ".srf", ".sr2",   # Sony
    ".raf",                   # Fujifilm
    ".orf",                   # Olympus / OM System
    ".rw2",                   # Panasonic
    ".pef",                   # Pentax
    ".raw", ".rwl",           # Leica
    ".3fr",                   # Hasselblad
}
IMAGE_EXTENSIONS = RAW_EXTENSIONS | {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# Color profiles offered on export. sRGB is built in to Pillow/LittleCMS;
# Adobe RGB and ProPhoto RGB need actual ICC profile files, bundled in
# assets/ rather than relying on whatever happens to be on the OS (Adobe
# RGB ships with macOS, but ProPhoto RGB doesn't, and neither is guaranteed
# on other platforms).
COLOR_PROFILES = ["sRGB", "Adobe RGB", "ProPhoto RGB"]

# Film stock types offered on the Colors tab. C-41 (color negative) and B&W
# negative both need the film-base division + density inversion below; E-6
# (color slide/reversal) is already a positive, so it skips the inversion.
FILM_MODES = ["C-41", "B&W", "E-6"]
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_PROFILE_FILES = {
    "Adobe RGB": os.path.join(_ASSETS_DIR, "AdobeRGB1998.icc"),
    "ProPhoto RGB": os.path.join(_ASSETS_DIR, "ProPhotoRGB.icc"),
}

# LibRaw's "flip" orientation code -> the PIL transpose that corrects for it.
# The embedded preview thumbnail a DNG carries is *not* pre-rotated the way
# postprocess()'s main image is, so this has to be applied by hand.
_FLIP_TO_TRANSPOSE = {0: None, 3: Image.ROTATE_180, 5: Image.ROTATE_90, 6: Image.ROTATE_270}

# Stops of density mapped to the full 0..1 output range. Roughly one stop
# of optical density (D=1.0, log2(10) ~= 3.32), a reasonable middle ground
# for C-41 stocks; Exposure/Contrast compensate for stock-to-stock variance.
DENSITY_RANGE = 3.32

# Auto Density / Auto Grade calibration, ported from NegPy's per-frame
# metering (docs/PIPELINE.md, "Automatic helpers" - NegPy is GPL-3, see
# auto_density_grade() below for how the two constants translate into this
# module's stops/density model instead of NegPy's own normalized domain).
ANCHOR_METER_STRENGTH = 0.2   # how far Exposure pulls the metered median toward mid-gray (0=none, 1=full correction)
ANCHOR_METER_BAND = 0.12      # that pull's cap, as a fraction of DENSITY_RANGE - keeps a deliberately low/high-key frame from being flattened to neutral
GRADE_NOMINAL_RATIO = 2.0     # DENSITY_RANGE / (P90-P10) for a "textbook normal" tonal histogram - the ~0.5-99.5th vs ~10-90th percentile span ratio of a roughly Gaussian distribution (z-score ratio 5.15/2.56 ~= 2.0), not tied to any particular exposure/contrast calibration. Recompute this if texture_lo_pct/texture_hi_pct below ever change.
GRADE_STRENGTH = 0.5          # 0 = same Contrast on every frame, 1 = every frame's textural range fully normalized to that statistical norm
SATURATION_BOOST_STRENGTH = 1.0   # fraction of the full contrast-coupled saturation boost auto_density_grade suggests - see its docstring; 1.0 is the calibrated match (not headroom to tune down casually - see the derivation there)
SATURATION_BOOST_MAX = 2.0        # cap on the suggested Saturation, so a very low Gamma can't push it to an implausible extreme

# Rec. 709 luma weights, used to hold brightness fixed while scaling
# chroma for the Saturation control.
LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass
class Params:
    mode: str = "C-41"        # one of FILM_MODES
    base_color: tuple = (0.85, 0.55, 0.35)  # typical orange mask guess
    exposure: float = 0.0     # stops, shifts the whole density image
    contrast: float = 1.0     # scales density spread around the mid pivot
    gamma: float = 1.0        # display gamma trim, applied after tone-mapping
    density: float = 0.0          # stops, shifts the whole image *after* contrast (unlike
                                   # exposure, not scaled by the Contrast slider)
    shadow_density: float = 0.0   # stops, added only in shadows (weighted by tone position)
    highlight_density: float = 0.0  # stops, added only in highlights (weighted by tone position)
    shift_r: float = 0.0      # per-channel density (color balance) shift, in stops
    shift_g: float = 0.0
    shift_b: float = 0.0
    saturation: float = 1.0   # chroma scale around luma, applied at the end
    denoise: float = 0.0      # median-filter grain reduction, applied before Sharpening
    sharpen: float = 0.0      # unsharp-mask amount, applied last on the final sRGB output

    def reset_adjustments(self):
        self.exposure = 0.0
        self.contrast = 1.0
        self.gamma = 1.0
        self.density = 0.0
        self.shadow_density = 0.0
        self.highlight_density = 0.0
        self.shift_r = 0.0
        self.shift_g = 0.0
        self.shift_b = 0.0
        self.saturation = 1.0
        self.denoise = 0.0
        self.sharpen = 0.0


def load_negative(path: str) -> tuple:
    """Load an image as a float32 RGB array in the 0..1 range.

    Returns (array, is_linear). Regular scans (JPEG/TIFF/PNG) are assumed
    sRGB gamma-encoded, like almost all image files. DNGs and native camera
    raw files are read through rawpy/libraw with no tone curve applied, so
    they come back already linear - see _load_raw_file for how scanner and
    camera sources are told apart and handled differently.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTENSIONS:
        return _load_raw_file(path), True
    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.float32) / 255.0, False


def _load_raw_file(path: str) -> np.ndarray:
    """Load a DNG or native camera raw file (CR2, NEF, ARW, RAF, ...).

    Two genuinely different kinds of file share this code path:

    - Scanner-style Linear DNGs (e.g. Nikon Coolscan via VueScan/SilverFast)
      carry already-assembled, non-mosaiced per-pixel RGB - there is no
      color filter array, so there's nothing to demosaic, and the scanner's
      3 output channels are already close to meaningful RGB on their own.
    - A real camera sensor (Bayer or X-Trans) instead stores one raw
      photosite reading per pixel, filtered through a color filter array
      (CFA); those channels are *not* display RGB by themselves and need
      demosaicing plus the camera's own white balance and color matrix
      (both embedded in the file, applied by LibRaw) to become meaningful
      color, the same way any raw photo editor processes a camera raw.

    LibRaw tells the two apart via the file's own CFA metadata (raw_pattern
    is a degenerate 1x1 "pattern" when there's no real mosaic, vs. a 2x2
    Bayer or larger X-Trans pattern when there is), so this doesn't need
    the caller to say which kind of file it's looking at.
    """
    try:
        import rawpy
    except ImportError as exc:
        raise RuntimeError(
            "Reading RAW/DNG files requires the 'rawpy' package. Install it with:\n"
            "    pip install rawpy"
        ) from exc

    with rawpy.imread(path) as raw:
        mosaiced = raw.raw_pattern is not None and raw.raw_pattern.size > 1
        if mosaiced:
            # Demosaicing happens automatically; camera white balance is
            # the best generally-available starting point, though it's
            # calibrated for photographing a lit scene rather than a
            # backlit negative on a copy stand, so it may need correcting
            # via the film-base pipette/color-balance sliders afterward,
            # same as an inaccurate orange-mask sample would.
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=True,
                gamma=(1, 1),
                output_bps=16,
                output_color=rawpy.ColorSpace.sRGB,
            )
        else:
            rgb16 = raw.postprocess(
                use_camera_wb=False,
                user_wb=[1.0, 1.0, 1.0, 1.0],
                no_auto_bright=True,
                gamma=(1, 1),
                output_bps=16,
                output_color=rawpy.ColorSpace.raw,
            )
    if rgb16.shape[-1] == 1:
        # B&W scanner DNGs carry a single raw channel (no CFA to debayer),
        # so postprocess() returns (H, W, 1) instead of (H, W, 3). Replicate
        # it to RGB so the rest of the pipeline - which assumes 3 channels
        # throughout - doesn't need a separate code path. A real camera
        # sensor always demosaics to 3 channels, so this only ever fires
        # for the non-mosaiced branch above.
        rgb16 = np.repeat(rgb16, 3, axis=-1)
    return rgb16.astype(np.float32) / 65535.0


def extract_thumbnail(path: str, max_dim: int = 160):
    """A small, fast preview for a filmstrip - or None if one can't be made.

    For DNGs this reads the embedded preview LibRaw already carries (a few
    milliseconds) instead of doing a full raw decode (hundreds of ms), so
    generating thumbnails for a whole folder synchronously stays fast. It's
    the raw negative's own preview - still orange-mask-tinted, not run
    through our conversion - since that requires a per-photo base color
    this function has no reason to know about.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in RAW_EXTENSIONS:
            import rawpy
            with rawpy.imread(path) as raw:
                thumb = raw.extract_thumb()
                flip = raw.sizes.flip
            if thumb.format == rawpy.ThumbFormat.JPEG:
                img = Image.open(io.BytesIO(thumb.data))
            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                img = Image.fromarray(thumb.data)
            else:
                return None
            op = _FLIP_TO_TRANSPOSE.get(flip)
            if op is not None:
                img = img.transpose(op)
        else:
            img = Image.open(path)
        img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim), Image.BILINEAR)
        return img
    except Exception:
        return None


def downscale(arr: np.ndarray, max_dim: int = 900, is_linear: bool = False) -> np.ndarray:
    """Downscale for the interactive preview.

    Resizing has to quantize to 8 bits along the way (PIL/uint8 round-trip).
    Doing that directly on *linear* data is destructive: linear-light values
    pack almost all of their detail into a narrow low range, so 256 levels
    there produces visible banding once our log/density math stretches it
    back out. Gamma-encode first (like a normal photo), quantize, then decode
    back to linear - the same precision budget a JPEG scan already gets.
    """
    h, w = arr.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return arr
    encoded = linear_to_srgb(arr) if is_linear else arr
    img = Image.fromarray((np.clip(encoded, 0.0, 1.0) * 255).astype(np.uint8))
    img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
    resized = np.asarray(img, dtype=np.float32) / 255.0
    return srgb_to_linear(resized) if is_linear else resized


def rotate90(arr: np.ndarray, quarters: int) -> np.ndarray:
    """Rotate an array by `quarters` * 90 degrees clockwise (0-3). Lossless -
    no resampling, just a re-indexing of the same pixels."""
    quarters = quarters % 4
    if quarters == 0:
        return arr
    return np.ascontiguousarray(np.rot90(arr, k=-quarters))


def rotate_arbitrary(arr: np.ndarray, angle_degrees: float) -> np.ndarray:
    """Rotate an array by an arbitrary angle (positive = clockwise), keeping
    the same canvas size. Corners the rotated content no longer covers are
    filled with black - callers crop those away (see
    crop.safe_crop_for_straighten) rather than showing them.
    """
    if abs(angle_degrees) < 1e-6:
        return arr
    from scipy import ndimage
    # ndimage.rotate's angle is counterclockwise; negate for our
    # positive-is-clockwise convention (a "straighten" slider tilting a
    # horizon level should turn the image clockwise for a positive value).
    return ndimage.rotate(arr, angle=-angle_degrees, axes=(0, 1), reshape=False,
                           order=1, mode="constant", cval=0.0).astype(arr.dtype)


def estimate_base_color(arr: np.ndarray) -> tuple:
    """Guess the film base color from the brightest (least dense) region.

    Picks pixels by overall luma rather than per-channel percentiles, so the
    three channel values come from the *same* physical spot instead of
    whichever pixels happen to be brightest in each channel independently
    (which can be different spots entirely - e.g. a blue sky highlight vs. a
    hot pixel - producing a nonsense, uncorrelated "base color"). The top
    sliver of the brightest pixels is excluded too, since that is usually
    sensor noise/clipping rather than the clear film itself, and the median
    (not mean/max) of what is left resists remaining outliers.
    """
    flat = arr.reshape(-1, 3)
    luma = flat.mean(axis=1)
    lo = np.percentile(luma, 97.0)
    hi = np.percentile(luma, 99.9)
    band = flat[(luma >= lo) & (luma <= hi)]
    if band.size == 0:
        band = flat[luma >= lo] if np.any(luma >= lo) else flat
    return tuple(float(v) for v in np.median(band, axis=0))


def auto_density_grade(arr: np.ndarray, base_color: tuple, is_linear: bool = False,
                        shadow_pct: float = 0.5, highlight_pct: float = 99.5,
                        texture_lo_pct: float = 10.0, texture_hi_pct: float = 90.0,
                        clip_floor: float = 0.01, mid_target: float = 0.214,
                        positive: bool = False) -> tuple:
    """Suggest (exposure, contrast, gamma, saturation) the way NegPy's Auto
    Density / Auto Grade meter a frame, ported into this module's stops/
    density model.

    NegPy runs Auto Density/Grade *after* a separate, always-on stage that
    stretches each frame's own black/white points to fill the working range
    - so its per-frame metering only has to add mood-aware fine tuning on
    top of an already-full-range image. This module has no such separate
    stage (Exposure/Contrast/Gamma *are* the whole tonal pipeline), so a
    literal, isolated port of just the fine-tuning step left images
    resting at (or near) `contrast=1.0` - i.e. barely stretched at all -
    whenever a frame's texture-percentile shape happened to look
    statistically "normal", regardless of whether its actual measured
    black/white points came anywhere near filling DENSITY_RANGE. That's
    what read as flat.

    So the shadow_pct-highlight_pct span (0.5-99.5 by default) still does
    the same unconditional full-range stretch/centering the old auto-levels
    did - that's the baseline every frame gets, punch included. NegPy's
    contribution is layered on top as a *damped modulation* of that
    baseline, not a replacement for it:

    - Auto Density (exposure): after the baseline centers the
      shadow_pct-highlight_pct window on mid-gray (DENSITY_RANGE / 2), the
      median is *also* only partially pulled the rest of the way to
      mid-gray - by ANCHOR_METER_STRENGTH, clamped to +-ANCHOR_METER_BAND
      of DENSITY_RANGE - so a deliberately low-key or high-key negative
      keeps its mood instead of being flattened to average brightness.
    - Auto Grade (contrast): the baseline contrast is scaled by how the
      frame's own textural spread (the texture_lo_pct-texture_hi_pct
      density range, P10-P90 by default) compares to GRADE_NOMINAL_RATIO -
      the shadow_pct-highlight_pct-to-texture spread ratio of a "textbook
      normal" tonal histogram - damped by GRADE_STRENGTH. A flat scene
      (texture narrower than normal) gets extra lift on top of the
      baseline stretch; a scene that's already punchy (texture close to
      the full span, e.g. a high-contrast silhouette) has that damped back
      toward the baseline instead of being pushed further.

    Gamma has no NegPy analog - NegPy's toe/shoulder H&D curve reshapes the
    tone nonlinearly instead, which this module doesn't have - so it's
    unchanged from the old auto-levels: a curves-style repositioning of the
    median within the shadow_pct-highlight_pct window onto mid_target
    (0.214 in scene-linear light, i.e. the classic 18%-gray reference),
    without moving the anchored black/white points. For most real photos
    this lands below 1.0 and is doing real contrast work - it's not a minor
    trim, and dropping it (an earlier version of this function did) is what
    made images read as flat despite the baseline stretch above.

    Saturation gets a suggested boost when Gamma lands below 1.0,
    compensating for a real effect that formula doesn't otherwise produce:
    on real film/paper, added contrast inherently pulls colors apart
    (that's why NegPy's own per-channel H&D curves need a "Dye Mute"
    control to tone the effect *back down*, rather than having none at
    all). `convert_linear()`'s gamma is deliberately tone-only - hue-safe
    but flat - so this suggests a uniform-across-tones Saturation lift
    instead, sized to match what a per-channel power curve x**(1/gamma)
    would have done to an average pixel's chroma/luma ratio: for a pure
    power law, chroma scales by the curve's local slope while luma follows
    the curve itself, and their ratio (slope * x / f(x)) reduces to exactly
    1/gamma regardless of x - so SATURATION_BOOST_STRENGTH is calibrated to
    1.0, not a fractional damping of that boost (a smaller value here
    quietly under-restores it - the pre-1.0 default did, and read as pale/
    desaturated next to the old per-channel gamma). SATURATION_BOOST_MAX
    still caps it, so a very low Gamma can't push it to an implausible
    extreme. Uniform, not tone-dependent, on purpose - an earlier version
    scaled each pixel's chroma by the gamma curve's local slope directly
    (not this ratio), which peaks near white and so amplified whatever
    small color cast sat in the highlights right along with genuine
    saturation, reintroducing the very cast this function's hue-safe gamma
    was meant to fix.

    `base_color` is only ever an estimate, and if it's off - notably if the
    frame has no true clear-film area to sample from - that shows up as a
    near-constant density offset; the baseline stretch self-corrects for
    that regardless of how good the base estimate was.

    Fully clipped pixels (any channel at or near raw zero - e.g. a blown sky)
    are excluded from all statistics first: density is +-log2(ratio), which
    shoots toward infinity as the raw value hits zero, so even a small
    clipped population can hijack a percentile and distort the whole result.

    `positive` must match the sign `convert_linear()` will use for this
    image's mode (True for E-6 slides, False for C-41/B&W negatives) - the
    percentiles below have to be taken in the same density direction the
    actual conversion applies, or the suggested exposure/contrast end up
    fitting the wrong end of the histogram.
    """
    base = np.array(base_color, dtype=np.float32)
    lin = arr if is_linear else srgb_to_linear(arr)
    base_lin = base if is_linear else srgb_to_linear(base)
    ratio = np.clip(lin / (base_lin + EPS), EPS, None)
    if positive:
        density_luma = (DENSITY_RANGE + np.log2(ratio)).mean(axis=-1)
    else:
        density_luma = (-np.log2(ratio)).mean(axis=-1)

    unclipped = ratio.min(axis=-1) > clip_floor
    sample = density_luma[unclipped] if np.count_nonzero(unclipped) >= density_luma.size // 20 else density_luma

    lo, p_lo, median, p_hi, hi = (float(v) for v in np.percentile(
        sample, [shadow_pct, texture_lo_pct, 50.0, texture_hi_pct, highlight_pct]))

    pivot = DENSITY_RANGE / 2.0
    span = max(hi - lo, EPS)
    baseline_contrast = DENSITY_RANGE / span
    baseline_exposure = (DENSITY_RANGE - hi - lo) / 2.0

    # Auto Density: the median, *after* the baseline centering above, only
    # partially pulled the rest of the way to mid-gray.
    band = ANCHOR_METER_BAND * DENSITY_RANGE
    shifted_median = median + baseline_exposure
    pull = float(np.clip(ANCHOR_METER_STRENGTH * (shifted_median - pivot), -band, band))
    exposure = float(np.clip(baseline_exposure - pull, -8.0, 8.0))

    # Auto Grade: baseline contrast scaled by a damped shape adjustment - 1.0
    # (no adjustment) when this frame's own full-span/texture-span ratio
    # matches GRADE_NOMINAL_RATIO, i.e. GRADE_NOMINAL_RATIO cancels out of
    # its own coefficient, the same relationship as NegPy's
    # `auto_grade_target (K) * auto_grade_nominal_ratio (n) == 1.0`.
    texture_range = max(p_hi - p_lo, EPS)
    shape_ratio = span / texture_range
    grade_adjust = 1.0 + (GRADE_STRENGTH / GRADE_NOMINAL_RATIO) * (shape_ratio - GRADE_NOMINAL_RATIO)
    contrast = float(np.clip(baseline_contrast * grade_adjust, 0.5, 2.5))

    # Gamma: reposition the median onto mid_target, same as the old
    # auto-levels (see docstring) - but measured after the *actual* Auto
    # Density/Auto Grade exposure and contrast above, not the pre-damping
    # baseline ones. Using the baseline stretch here (an earlier version of
    # this function did) silently breaks the mid_target guarantee: gamma
    # solves for whatever value m satisfies m ** (1/gamma) == mid_target,
    # so it only lands the median on mid_target if m is where the median
    # *actually* falls pre-gamma - and once Auto Density/Grade pull exposure
    # and contrast away from the naive full-window stretch, that's no
    # longer the same thing whenever the median doesn't already sit dead
    # center in [lo, hi] (i.e. most real, non-flat photos).
    density_median = (median + exposure - pivot) * contrast + pivot
    normalized_median = min(max(density_median / DENSITY_RANGE, EPS), 1.0 - EPS)
    if abs(normalized_median - mid_target) < EPS:
        gamma = 1.0
    else:
        gamma = float(np.log(normalized_median) / np.log(mid_target))
    gamma = float(np.clip(gamma, 0.3, 2.5))

    # Saturation: a uniform-across-tones compensation for gamma's
    # tone-only, hue-safe curve not otherwise reproducing added contrast's
    # natural saturation boost - see docstring.
    saturation = 1.0 + SATURATION_BOOST_STRENGTH * max(0.0, (1.0 / gamma) - 1.0)
    saturation = float(np.clip(saturation, 1.0, SATURATION_BOOST_MAX))

    return exposure, contrast, gamma, saturation


def sample_base_color(arr: np.ndarray, x: int, y: int, radius: int = 4) -> tuple:
    """Average a small block around (x, y) in image pixel coordinates."""
    h, w = arr.shape[:2]
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)
    block = arr[y0:y1, x0:x1].reshape(-1, 3)
    return tuple(float(v) for v in block.mean(axis=0))


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def convert_linear(arr: np.ndarray, params: Params, is_linear: bool = False) -> np.ndarray:
    """Run the full negative->positive pipeline, stopping *before* the final
    sRGB gamma encode. Returns float32 0..1 linear-light RGB.

    `convert()` just gamma-encodes this for display/standard image formats.
    DNG export needs the linear version directly: a DNG's LinearRaw data is
    defined to be actual linear light, so gamma-encoded values written into
    one would make every raw-processing tool that opens it apply its own
    linear-to-display rendering on top of already-display-encoded data.
    """
    base = np.array(params.base_color, dtype=np.float32)

    lin = arr if is_linear else srgb_to_linear(arr)
    base_lin = base if is_linear else srgb_to_linear(base)

    ratio = np.clip(lin / (base_lin + EPS), EPS, None)
    # ~0 at the film base, grows with exposure. E-6 slides are already a
    # positive - bright scan = bright scene - so density has to grow with
    # scan *brightness* there instead, anchored so the sampled reference
    # (ratio ~= 1, e.g. a clear/highlight area) lands at DENSITY_RANGE
    # (full white) rather than at 0 (black), the opposite anchor from a
    # negative's clear film base.
    if params.mode == "E-6":
        density = DENSITY_RANGE + np.log2(ratio)
    else:
        density = -np.log2(ratio)

    # Color balance is an *additive* per-channel density shift, not a
    # multiplicative gain: density can be negative (e.g. a pixel slightly
    # brighter than the sampled base - common near highlights or noise),
    # and multiplying a negative value by a larger gain pushes it further
    # *away* from zero - the opposite direction from what happens to the
    # (much more common) positive-density pixels. That made the same slider
    # move increase color in most of the image but decrease it in some
    # spots, depending on the mix of pixel signs in that particular image.
    # An additive shift moves every pixel the same direction regardless of
    # its density's sign.
    shifts = np.array([params.shift_r, params.shift_g, params.shift_b], dtype=np.float32)
    density = density + shifts

    density = density + params.exposure

    pivot = DENSITY_RANGE / 2.0
    density = (density - pivot) * params.contrast + pivot

    # Master density shift, applied *after* the contrast scale above - unlike
    # Exposure (shifted in before that scale, so Contrast amplifies or damps
    # its effect), this moves the whole image by a fixed amount regardless of
    # the Contrast slider, like adjusting a print's exposure after the
    # negative's contrast grade is already fixed.
    density = density + params.density

    # Shadow/Highlight Density: independent stops shifts weighted by each
    # pixel's own tone position, so they act like a local, one-sided
    # exposure change - lifting/lowering just the shadows or just the
    # highlights without touching the other end or the midtones as much.
    # `normalized` is a 0..1 proxy for output tone (0 = darkest, 1 =
    # brightest) computed *before* those two adjustments are added, so their
    # own contribution doesn't feed back into their own weighting.
    if params.shadow_density != 0.0 or params.highlight_density != 0.0:
        normalized = np.clip(density / DENSITY_RANGE, 0.0, 1.0)
        shadow_weight = (1.0 - normalized) ** 2
        highlight_weight = normalized ** 2
        density = density + params.shadow_density * shadow_weight
        density = density + params.highlight_density * highlight_weight

    output_linear = np.clip(density / DENSITY_RANGE, 0.0, 1.0)
    if params.gamma != 1.0:
        # Apply the gamma curve to luma, then rescale each pixel's RGB to
        # match - preserves hue and (HSV-style, ratio) saturation exactly.
        # The old per-channel power curve (output_linear ** (1/gamma))
        # doesn't: raising each channel independently stretches the ratio
        # between them apart whenever they differ, so whichever channel
        # already read highest (e.g. blue in a cool or sky-heavy scene) got
        # pushed disproportionately further from the others - amplifying
        # any residual color cast, worst exactly in near-neutral highlights
        # where a cast reads most visibly. A per-pixel chroma boost tied to
        # the curve's local slope (tried here previously) has the same
        # problem from the other direction: slope peaks near white, so it
        # amplifies whatever small cast sits in the highlights too. Kept
        # deliberately dumb/tone-only here; auto_density_grade's Saturation
        # suggestion (see there) is the one place a deliberate, uniform-
        # across-tones boost gets added back in.
        luma = np.dot(output_linear, LUMA_WEIGHTS)
        target_luma = np.power(np.clip(luma, EPS, 1.0), 1.0 / max(params.gamma, EPS))
        scale = np.where(luma > EPS, target_luma / np.maximum(luma, EPS), 1.0)
        output_linear = np.clip(output_linear * scale[..., None], 0.0, 1.0)

    if params.mode == "B&W":
        # Collapse to true neutral gray - not just desaturated - regardless
        # of the Saturation slider, using the same luma weights it uses.
        # (The per-channel Red/Green/Blue shifts above still apply before
        # this, acting like colored filters on a B&W enlarger.)
        luma = np.dot(output_linear, LUMA_WEIGHTS)
        output_linear = np.repeat(luma[..., None], 3, axis=-1)

    if params.saturation != 1.0:
        luma = np.dot(output_linear, LUMA_WEIGHTS)[..., None]
        output_linear = np.clip(luma + (output_linear - luma) * params.saturation, 0.0, 1.0)

    return output_linear


def apply_denoise(arr: np.ndarray, amount: float) -> np.ndarray:
    """Reduce grain/noise with a median filter - good at knocking down the
    speckled, salt-and-pepper look of high-ISO/pushed C-41 grain while still
    respecting hard edges, unlike a plain blur which would soften everything
    equally.

    `amount` blends it in over 0..1 (a 3x3 filter), then over 1..2 blends
    from that into a 5x5 filter - a wider radius for heavier grain than a
    fixed small filter can fully knock down, without a discontinuous jump
    where the filter size switches.

    Applied on the final sRGB output, *before* Sharpening: sharpening a
    still-noisy image re-amplifies the grain, so denoising has to happen
    first for the two controls to work together rather than fight.
    """
    if amount <= 0:
        return arr
    from scipy import ndimage
    med3 = ndimage.median_filter(arr, size=(3, 3, 1))
    if amount <= 1.0:
        return arr + (med3 - arr) * amount
    med5 = ndimage.median_filter(arr, size=(5, 5, 1))
    extra = min(amount - 1.0, 1.0)
    return med3 + (med5 - med3) * extra


def apply_sharpen(arr: np.ndarray, amount: float, radius: float = 1.5, threshold: float = 0.02) -> np.ndarray:
    """Unsharp mask: boost local (edge/detail) contrast without touching the
    overall tonal balance - what makes a scan look "washy" is often a lack
    of this, not wrong exposure/contrast, since those only affect the
    overall tonal curve, not per-pixel acutance.

    Applied on the final sRGB output rather than the linear-light density
    result: sharpening is inherently a perceptual/display-space operation,
    and doing it on scene-linear values produces unnatural-looking halos.
    `threshold` leaves very low-contrast (flat/noisy) areas alone, so film
    grain doesn't get emphasized into speckle.
    """
    if amount <= 0:
        return arr
    from scipy import ndimage
    blurred = ndimage.gaussian_filter(arr, sigma=(radius, radius, 0))
    diff = arr - blurred
    mask = np.abs(diff) >= threshold
    sharpened = arr + diff * amount * mask
    return np.clip(sharpened, 0.0, 1.0)


def convert(arr: np.ndarray, params: Params, is_linear: bool = False) -> np.ndarray:
    """Apply the full negative->positive pipeline. Returns float32 0..1 sRGB."""
    output_linear = convert_linear(arr, params, is_linear)
    output = np.clip(linear_to_srgb(output_linear), 0.0, 1.0)
    output = apply_denoise(output, params.denoise)
    return apply_sharpen(output, params.sharpen)


def to_uint8(arr: np.ndarray) -> np.ndarray:
    return (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


# XYZ(D65) -> linear-sRGB primaries. DNG's ColorMatrix1 is defined as the
# matrix from the profile connection space (XYZ, under CalibrationIlluminant1)
# to "camera native" RGB - since our data already *is* linear sRGB primaries,
# that's exactly this well-known standard matrix (Bruce Lindbloom's XYZ->sRGB).
_XYZ_TO_SRGB = (
    3.2404542, -1.5371385, -0.4985314,
    -0.9692660, 1.8760108, 0.0415560,
    0.0556434, -0.2040259, 1.0572252,
)
_D65_ILLUMINANT = 21  # DNG LightSource enum value for D65


def _to_rational_pairs(values, scale=1_000_000):
    flat = []
    for v in values:
        flat.append(int(round(v * scale)))
        flat.append(scale)
    return flat


def save_linear_dng(path: str, linear_rgb: np.ndarray) -> None:
    """Save a converted positive as a 16-bit "Linear DNG": non-mosaiced raw
    data (PhotometricInterpretation=LinearRaw), openable in Lightroom,
    Capture One, or darktable as a raw file and given further raw-style
    adjustment (exposure, white balance, highlight recovery) there, rather
    than being a final "baked" image the way a TIFF/PNG/JPEG export is.

    `linear_rgb` must be *linear light* (e.g. from `convert_linear()`, not
    `convert()`) - a DNG's LinearRaw data is defined to be linear, and
    writing gamma-encoded values into one would make raw-processing tools
    apply their own linear-to-display rendering on top of already-encoded
    data, effectively double-encoding it.
    """
    try:
        import tifffile
    except ImportError as exc:
        raise RuntimeError(
            "Saving a DNG requires the 'tifffile' package. Install it with:\n"
            "    pip install tifffile"
        ) from exc

    data16 = (np.clip(linear_rgb, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)

    extratags = [
        (254, 4, 1, 0, False),                                      # NewSubfileType: 0 = main image.
        # ^ Baseline TIFF tag every DNG needs to mark "this is the full
        # image, not a thumbnail/preview" - without it, Adobe's strict
        # parser refuses the file outright even though more lenient
        # readers (LibRaw, darktable's rawspeed) just assume 0 and open
        # it fine, which is exactly the darktable-yes/Lightroom-no split.
        (271, 2, 0, "NegConvert", False),                           # Make
        (272, 2, 0, "NegConvert", False),                           # Model
        (274, 3, 1, 1, False),                                      # Orientation: 1 = normal
        (50706, 1, 4, (1, 4, 0, 0), False),                         # DNGVersion
        (50707, 1, 4, (1, 1, 0, 0), False),                         # DNGBackwardVersion
        (50708, 2, 0, "NegConvert", False),                         # UniqueCameraModel
        (50721, 10, 9, _to_rational_pairs(_XYZ_TO_SRGB), False),    # ColorMatrix1
        (50728, 5, 3, _to_rational_pairs([1.0, 1.0, 1.0]), False),  # AsShotNeutral
        (50778, 3, 1, _D65_ILLUMINANT, False),                      # CalibrationIlluminant1
        (50714, 4, 1, 0, False),                                    # BlackLevel
        (50717, 4, 1, 65535, False),                                # WhiteLevel
    ]
    # photometric must be the actual PHOTOMETRIC.LINEAR_RAW enum/int (34892),
    # not the string "linear_raw" - tifffile silently accepts an unrecognized
    # string but then can't use it to infer which shape axes are the image
    # vs. extra pages, and misreads a (H, W, 3) array as H separate
    # single-channel (W, 3) pages instead of one (H, W, 3) image. And even
    # with the correct enum, tifffile doesn't special-case this DNG-specific
    # value the way it does standard RGB, so planarconfig="contig" still has
    # to be passed explicitly to say "the last axis is interleaved channels,
    # not more pages" - metadata=None suppresses tifffile's default
    # ImageDescription (a JSON blob describing the array shape), noise a
    # strict DNG parser doesn't expect and has no reason to need. Likewise,
    # tifffile doesn't know LinearRaw's 3 samples are plain RGB, so left to
    # its own defaults it tags 2 of them as ExtraSamples (unspecified extra
    # channels) - which throws off Adobe's raw pipeline enough that Camera
    # Raw/Lightroom refuse the file as an "unknown camera model" rather than
    # reading it as a normal 3-channel raw image. extrasamples=False stops
    # tifffile writing that tag.
    tifffile.imwrite(path, data16, photometric=tifffile.PHOTOMETRIC.LINEAR_RAW,
                      planarconfig="contig", extrasamples=False,
                      extratags=extratags, metadata=None)


def convert_to_profile(rgb_uint8: np.ndarray, profile_name: str):
    """Convert an sRGB uint8 image (our `convert()` output) to another
    working color space's primaries and tone curve, for export.

    Returns (converted_uint8_array, icc_profile_bytes). The pixel values
    genuinely need remapping, not just a profile tag swap: Adobe RGB and
    ProPhoto RGB have different primaries (a wider gamut) and different
    tone curves than sRGB, so the same stored numbers mean a different
    color in each space. LittleCMS (via PIL.ImageCms) does that transform
    accurately; we just supply the source (sRGB) and destination profiles.
    `icc_profile_bytes` must be embedded in the saved file so viewers know
    how to interpret the (now non-sRGB) pixel values.
    """
    from PIL import ImageCms

    src_profile = ImageCms.createProfile("sRGB")

    if profile_name == "sRGB" or profile_name not in _PROFILE_FILES:
        icc_bytes = ImageCms.ImageCmsProfile(src_profile).tobytes()
        return rgb_uint8, icc_bytes

    dst_profile = ImageCms.getOpenProfile(_PROFILE_FILES[profile_name])
    img = Image.fromarray(rgb_uint8, mode="RGB")
    converted = ImageCms.profileToProfile(
        img, src_profile, dst_profile,
        renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
        outputMode="RGB",
    )
    icc_bytes = dst_profile.tobytes()
    return np.asarray(converted), icc_bytes
