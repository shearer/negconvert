"""Core C-41 negative -> positive conversion math.

Pipeline: sample the clear film base (the orange mask) from an unexposed
area of the scan, divide the negative by that color to neutralize the
mask, invert, then apply exposure/contrast/gamma and per-channel trim.
"""
import os
from dataclasses import dataclass

import numpy as np
from PIL import Image

EPS = 1e-6
RAW_EXTENSIONS = {".dng"}


@dataclass
class Params:
    base_color: tuple = (0.85, 0.55, 0.35)  # typical orange mask guess
    exposure: float = 1.0
    contrast: float = 1.2
    gamma: float = 2.2
    gain_r: float = 1.0
    gain_g: float = 1.0
    gain_b: float = 1.0

    def reset_adjustments(self):
        self.exposure = 1.0
        self.contrast = 1.2
        self.gamma = 2.2
        self.gain_r = 1.0
        self.gain_g = 1.0
        self.gain_b = 1.0


def load_negative(path: str) -> np.ndarray:
    """Load an image as a float32 RGB array in the 0..1 range.

    Scanner DNGs (e.g. Nikon Coolscan 5 ED via VueScan/SilverFast) are read
    through rawpy/libraw as unprocessed as possible, since our own base-color
    division expects raw, scanner-proportional RGB values rather than a
    camera-style rendered image.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTENSIONS:
        return _load_dng(path)
    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.float32) / 255.0


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
    """Guess the film base color from the brightest (least dense) pixels."""
    flat = arr.reshape(-1, 3)
    hi = np.percentile(flat, 99, axis=0)
    return tuple(float(v) for v in hi)


def sample_base_color(arr: np.ndarray, x: int, y: int, radius: int = 4) -> tuple:
    """Average a small block around (x, y) in image pixel coordinates."""
    h, w = arr.shape[:2]
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)
    block = arr[y0:y1, x0:x1].reshape(-1, 3)
    return tuple(float(v) for v in block.mean(axis=0))


def convert(arr: np.ndarray, params: Params) -> np.ndarray:
    """Apply the full negative->positive pipeline. Returns float32 0..1 RGB."""
    base = np.array(params.base_color, dtype=np.float32)
    norm = arr / (base + EPS)
    norm = norm * params.exposure

    positive = 1.0 - norm
    positive = np.clip(positive, 0.0, 1.0)

    gains = np.array([params.gain_r, params.gain_g, params.gain_b], dtype=np.float32)
    positive = np.clip(positive * gains, 0.0, 1.0)

    positive = (positive - 0.5) * params.contrast + 0.5
    positive = np.clip(positive, 0.0, 1.0)

    positive = np.power(positive, 1.0 / max(params.gamma, EPS))
    return np.clip(positive, 0.0, 1.0)


def to_uint8(arr: np.ndarray) -> np.ndarray:
    return (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
