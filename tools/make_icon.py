#!/usr/bin/env python3
"""Generate the NegConvert app icon: a Photoshop/Lightroom-style rounded
square, dark grey, with a bold "NC" monogram in Kodak yellow.

Run this, then (on macOS) build the .icns with:
    python3 tools/make_icon.py
    bash tools/build_icns.sh
"""
import os

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
CORNER_RADIUS = int(SIZE * 0.18)  # matches the modern macOS "squircle" app-icon proportion
BG_TOP = (58, 58, 58, 255)      # dark grey, subtle gradient for depth (like Ps/Lr icons)
BG_BOTTOM = (38, 38, 38, 255)
KODAK_YELLOW = (255, 204, 0, 255)
TEXT = "NC"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")


def make_icon():
    # vertical gradient background, drawn full-bleed then masked to a rounded rect
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        grad_draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (SIZE - 1, SIZE - 1)], radius=CORNER_RADIUS, fill=255)

    base.paste(gradient, (0, 0), mask)

    # subtle 1px lighter inner edge highlight, like Adobe's icons have
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([(0, 0), (SIZE - 1, SIZE - 1)], radius=CORNER_RADIUS,
                            outline=(255, 255, 255, 30), width=3)

    # "NC" monogram, bold, centered
    font_size = int(SIZE * 0.46)
    font = ImageFont.truetype(FONT_PATH, font_size)
    bbox = draw.textbbox((0, 0), TEXT, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((SIZE - text_w) / 2 - bbox[0], (SIZE - text_h) / 2 - bbox[1])
    draw.text(pos, TEXT, font=font, fill=KODAK_YELLOW)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "icon_1024.png")
    base.save(out_path)
    print("wrote", out_path)
    return base


if __name__ == "__main__":
    make_icon()
