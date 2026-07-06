"""Pure geometry for the crop tool: aspect-ratio presets and fractional
crop-rect math. Crop rects are stored as (fx0, fy0, fx1, fy1), each in
0..1, relative to the *full* image - resolution independent, so the same
rect applies to the preview and the full-res export alike.
"""
import math

# (label, width/height ratio - None means unconstrained "Free")
ASPECT_PRESETS = [
    ("Free", None),
    ("1:1  Square (6x6)", 1 / 1),
    ("3:2  35mm", 3 / 2),
    ("2:3  35mm portrait", 2 / 3),
    ("4:3  645", 4 / 3),
    ("3:4  645 portrait", 3 / 4),
    ("16:9  Wide", 16 / 9),
    ("9:16  Tall", 9 / 16),
    ("5:4  Large format", 5 / 4),
    ("4:5  Large format portrait", 4 / 5),
]

FULL_RECT = (0.0, 0.0, 1.0, 1.0)
MIN_SIZE = 0.02  # smallest allowed crop dimension, as a fraction of the image


def crop_pixel_box(shape, rect):
    """Convert a fractional (fx0,fy0,fx1,fy1) rect to pixel bounds (x0,y0,x1,y1)
    for an array of the given (h, w, ...) shape."""
    h, w = shape[:2]
    fx0, fy0, fx1, fy1 = rect
    x0 = int(round(min(fx0, fx1) * w))
    x1 = int(round(max(fx0, fx1) * w))
    y0 = int(round(min(fy0, fy1) * h))
    y1 = int(round(max(fy0, fy1) * h))
    x0 = max(0, min(x0, w - 1))
    y0 = max(0, min(y0, h - 1))
    x1 = max(x0 + 1, min(x1, w))
    y1 = max(y0 + 1, min(y1, h))
    return x0, y0, x1, y1


def clamp_range(a, b, lo=0.0, hi=1.0):
    """Shift/shrink the interval [a, b] to fit inside [lo, hi]."""
    span = b - a
    if span >= hi - lo:
        return lo, hi
    if a < lo:
        a, b = lo, lo + span
    elif b > hi:
        a, b = hi - span, hi
    return a, b


def fit_rect_to_ratio(rect, ratio, img_w_px, img_h_px):
    """Resize `rect` (fractional) to match `ratio` (w/h), keeping its center
    fixed and clipping to image bounds. `ratio=None` returns rect unchanged."""
    if ratio is None:
        return rect
    fx0, fy0, fx1, fy1 = rect
    cx, cy = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    cur_w_px = (fx1 - fx0) * img_w_px
    cur_h_px = (fy1 - fy0) * img_h_px

    if cur_h_px <= 0:
        new_w_px, new_h_px = cur_w_px, cur_w_px / ratio
    elif cur_w_px / cur_h_px > ratio:
        new_h_px = cur_h_px
        new_w_px = new_h_px * ratio
    else:
        new_w_px = cur_w_px
        new_h_px = new_w_px / ratio

    new_fw = new_w_px / img_w_px
    new_fh = new_h_px / img_h_px
    fx0n, fx1n = clamp_range(cx - new_fw / 2, cx + new_fw / 2)
    fy0n, fy1n = clamp_range(cy - new_fh / 2, cy + new_fh / 2)
    return fx0n, fy0n, fx1n, fy1n


def resize_corner(anchor, drag, ratio, img_w_px, img_h_px):
    """Given a fixed (anchor_x, anchor_y) opposite corner and a freely
    dragged (drag_x, drag_y) point, return the new dragged-corner position.

    With no ratio constraint, the drag point is returned as-is (already
    clamped by the caller). With a ratio, whichever axis moved further
    (in pixels) drives the box size, the other axis is derived to match
    the ratio, and the result is scaled back proportionally if it would
    push the box outside the image bounds.
    """
    if ratio is None:
        return drag

    anchor_x, anchor_y = anchor
    drag_x, drag_y = drag
    dx_px = (drag_x - anchor_x) * img_w_px
    dy_px = (drag_y - anchor_y) * img_h_px

    if dx_px == 0 and dy_px == 0:
        return anchor_x, anchor_y

    if abs(dx_px) >= abs(dy_px) * ratio:
        new_dx_px = dx_px
        sign_y = 1.0 if dy_px >= 0 else -1.0
        new_dy_px = sign_y * abs(new_dx_px) / ratio
    else:
        new_dy_px = dy_px
        sign_x = 1.0 if dx_px >= 0 else -1.0
        new_dx_px = sign_x * abs(new_dy_px) * ratio

    scale = 1.0
    nx = anchor_x + new_dx_px / img_w_px
    ny = anchor_y + new_dy_px / img_h_px
    if nx < 0.0:
        scale = min(scale, (anchor_x - 0.0) / max(abs(new_dx_px / img_w_px), 1e-9))
    if nx > 1.0:
        scale = min(scale, (1.0 - anchor_x) / max(abs(new_dx_px / img_w_px), 1e-9))
    if ny < 0.0:
        scale = min(scale, (anchor_y - 0.0) / max(abs(new_dy_px / img_h_px), 1e-9))
    if ny > 1.0:
        scale = min(scale, (1.0 - anchor_y) / max(abs(new_dy_px / img_h_px), 1e-9))
    new_dx_px *= scale
    new_dy_px *= scale
    return anchor_x + new_dx_px / img_w_px, anchor_y + new_dy_px / img_h_px


def rotated_rect_max_area(w, h, angle_radians):
    """The largest axis-aligned rectangle that fits inside a w x h rectangle
    after it's been rotated by `angle_radians`, without covering any of the
    now-empty corners. Standard result for this (search "largest rectangle
    inscribed in a rotated rectangle"); used to auto-size the crop box after
    straightening so no black corners show.
    """
    if w <= 0 or h <= 0:
        return 0.0, 0.0

    width_is_longer = w >= h
    side_long, side_short = (w, h) if width_is_longer else (h, w)

    sin_a, cos_a = abs(math.sin(angle_radians)), abs(math.cos(angle_radians))
    if side_short <= 2.0 * sin_a * cos_a * side_long or abs(sin_a - cos_a) < 1e-10:
        # "half-constrained" case: two crop corners touch the long side,
        # the other two sit on the midline parallel to it.
        x = 0.5 * side_short
        if width_is_longer:
            wr, hr = x / sin_a, x / cos_a
        else:
            wr, hr = x / cos_a, x / sin_a
    else:
        # fully-constrained case: the crop touches all four sides.
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr = (w * cos_a - h * sin_a) / cos_2a
        hr = (h * cos_a - w * sin_a) / cos_2a
    return wr, hr


def safe_crop_for_straighten(angle_degrees, img_w_px, img_h_px):
    """The centered fractional crop rect with no empty corners after
    rotating a img_w_px x img_h_px image by `angle_degrees`. Returns
    FULL_RECT for (near) zero angle."""
    if abs(angle_degrees) < 1e-6:
        return FULL_RECT
    wr, hr = rotated_rect_max_area(img_w_px, img_h_px, math.radians(angle_degrees))
    fw = min(max(wr / img_w_px, MIN_SIZE), 1.0)
    fh = min(max(hr / img_h_px, MIN_SIZE), 1.0)
    return (0.5 - fw / 2, 0.5 - fh / 2, 0.5 + fw / 2, 0.5 + fh / 2)
