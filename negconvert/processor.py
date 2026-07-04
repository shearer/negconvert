"""Core C-41 negative -> positive conversion math.

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
   (0 at the film base, increasing with exposure).
3. Apply per-channel density gain (color balance), an exposure shift, and
   a contrast scale - all in density/stops space.
4. Map density back to a displayable 0..1 range, apply a gamma trim, and
   re-encode to sRGB for viewing/saving.
"""
import os
from dataclasses import dataclass

import numpy as np
from PIL import Image

EPS = 1e-6
RAW_EXTENSIONS = {".dng"}

# Stops of density mapped to the full 0..1 output range. Roughly one stop
# of optical density (D=1.0, log2(10) ~= 3.32), a reasonable middle ground
# for C-41 stocks; Exposure/Contrast compensate for stock-to-stock variance.
DENSITY_RANGE = 3.32


@dataclass
class Params:
    base_color: tuple = (0.85, 0.55, 0.35)  # typical orange mask guess
    exposure: float = 0.0     # stops, shifts the whole density image
    contrast: float = 1.0     # scales density spread around the mid pivot
    gamma: float = 1.0        # display gamma trim, applied after tone-mapping
    gain_r: float = 1.0       # per-channel density (color balance) multiplier
    gain_g: float = 1.0
    gain_b: float = 1.0

    def reset_adjustments(self):
        self.exposure = 0.0
        self.contrast = 1.0
        self.gamma = 1.0
        self.gain_r = 1.0
        self.gain_g = 1.0
        self.gain_b = 1.0


def load_negative(path: str) -> tuple:
    """Load an image as a float32 RGB array in the 0..1 range.

    Returns (array, is_linear). Regular scans (JPEG/TIFF/PNG) are assumed
    sRGB gamma-encoded, like almost all image files. Scanner DNGs (e.g.
    Nikon Coolscan 5 ED via VueScan/SilverFast) are read through rawpy/
    libraw with no tone curve applied, so they come back already linear.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTENSIONS:
        return _load_dng(path), True
    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.float32) / 255.0, False


def _load_dng(path: str) -> np.ndarray:
    try:
        import rawpy
    except ImportError as exc:
        raise RuntimeError(
            "Reading DNG files requires the 'rawpy' package. Install it with:\n"
            "    pip install rawpy"
        ) from exc

    with rawpy.imread(path) as raw:
        # Coolscan-style scanner DNGs are linear (non-mosaiced) raw data, so
        # there is no debayering to do; we just want the sensor-proportional
        # values with no white balance, color matrix, or tone curve applied.
        rgb16 = raw.postprocess(
            use_camera_wb=False,
            user_wb=[1.0, 1.0, 1.0, 1.0],
            no_auto_bright=True,
            gamma=(1, 1),
            output_bps=16,
            output_color=rawpy.ColorSpace.raw,
        )
    return rgb16.astype(np.float32) / 65535.0


def downscale(arr: np.ndarray, max_dim: int = 900) -> np.ndarray:
    h, w = arr.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return arr
    img = Image.fromarray((arr * 255).astype(np.uint8))
    img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
    return np.asarray(img, dtype=np.float32) / 255.0


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


def convert(arr: np.ndarray, params: Params, is_linear: bool = False) -> np.ndarray:
    """Apply the full negative->positive pipeline. Returns float32 0..1 sRGB."""
    base = np.array(params.base_color, dtype=np.float32)

    lin = arr if is_linear else srgb_to_linear(arr)
    base_lin = base if is_linear else srgb_to_linear(base)

    ratio = np.clip(lin / (base_lin + EPS), EPS, None)
    density = -np.log2(ratio)  # ~0 at the film base, grows with exposure

    gains = np.array([params.gain_r, params.gain_g, params.gain_b], dtype=np.float32)
    density = density * gains

    density = density + params.exposure

    pivot = DENSITY_RANGE / 2.0
    density = (density - pivot) * params.contrast + pivot

    output_linear = np.clip(density / DENSITY_RANGE, 0.0, 1.0)
    output_linear = np.power(output_linear, 1.0 / max(params.gamma, EPS))

    output = linear_to_srgb(output_linear)
    return np.clip(output, 0.0, 1.0)


def to_uint8(arr: np.ndarray) -> np.ndarray:
    return (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
